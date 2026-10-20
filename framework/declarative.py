"""YAML 模块收集、变量替换和接口/Web 步骤执行，不执行配置中的 Python。"""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import os
import re
import time
from uuid import uuid4
import pytest
import yaml
from playwright.sync_api import expect
from framework.assertions import assert_status, assert_json_value, assert_json_type, assert_duration, json_value
from framework.steps import step

VARIABLE = re.compile(r"\$\{([^{}]+)\}")
MODULE = re.compile(r"^[\w-]+$", re.UNICODE)
TYPES = {"str": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict, "null": type(None)}
WEB_ACTIONS = {"goto", "fill", "click", "check", "uncheck", "select", "press", "assert_text", "assert_title", "assert_url", "assert_visible", "assert_hidden", "assert_value"}


def mapping(value, location):
    if not isinstance(value, dict):
        raise ValueError(f"{location} 必须是键值配置")
    return value


def keys(value, allowed, location):
    mapping(value, location)
    unknown = set(value) - set(allowed)
    if unknown:
        raise ValueError(f"{location} 存在不支持的字段：{', '.join(sorted(unknown))}")


def read_yaml(path):
    try:
        return mapping(yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}, str(path))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"读取模块配置失败：{path.name}：{exc}") from exc


def expand_steps(steps, flows, stack=()):
    if not isinstance(steps, list):
        raise ValueError("步骤必须是列表")
    result = []
    for entry in steps:
        keys(entry, {"api", "web", "use", "when_defined"}, "步骤")
        if sum(k in entry for k in ("api", "web", "use")) != 1:
            raise ValueError("每个步骤必须且只能填写 api、web 或 use 其中一项")
        if "use" in entry:
            name = entry["use"]
            if not isinstance(name, str) or name not in flows:
                raise ValueError(f"公共流程不存在：{name}")
            if name in stack or len(stack) >= 16:
                raise ValueError(f"公共流程循环引用或嵌套过深：{' → '.join((*stack, name))}")
            expanded = expand_steps(flows[name], flows, (*stack, name))
            for child in expanded:
                child = deepcopy(child)
                if "when_defined" in entry:
                    child["when_defined"] = entry["when_defined"]
                result.append(child)
        else:
            result.append(deepcopy(entry))
    return result


def validate_step(entry):
    if "when_defined" in entry and not isinstance(entry["when_defined"], str):
        raise ValueError("when_defined 必须是变量名")
    if "api" in entry:
        spec = entry["api"]
        keys(spec, {"method", "path", "json", "data", "params", "headers", "form", "expect", "extract"}, "接口步骤")
        if not isinstance(spec.get("path"), str) or not spec["path"]:
            raise ValueError("接口步骤必须填写 path")
        method = spec.get("method", "GET")
        if not isinstance(method, str) or method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            raise ValueError("接口 method 不受支持")
        if sum(k in spec for k in ("json", "data", "form")) > 1:
            raise ValueError("接口 json、data、form 只能选择一种请求体")
        assertion = spec.get("expect", {})
        keys(assertion, {"status", "json", "types", "contains", "headers", "max_ms"}, "接口断言")
        for name in ("json", "types", "headers"):
            if name in assertion:
                mapping(assertion[name], f"断言 {name}")
        for value in assertion.get("types", {}).values():
            if value not in TYPES:
                raise ValueError(f"断言类型必须是 {', '.join(TYPES)} 之一")
        for name, extraction in mapping(spec.get("extract", {}), "extract").items():
            if not isinstance(name, str) or not name:
                raise ValueError("提取变量名必须是非空字符串")
            if isinstance(extraction, str):
                if not extraction:
                    raise ValueError("提取路径不可为空")
            else:
                keys(extraction, {"path", "sensitive"}, "变量提取")
                if not isinstance(extraction.get("path"), str) or not extraction["path"]:
                    raise ValueError("提取 path 必须是非空字符串")
                if type(extraction.get("sensitive", False)) is not bool:
                    raise ValueError("提取 sensitive 必须为 true 或 false")
        return any(k in assertion for k in ("status", "contains", "max_ms")) or any(bool(assertion.get(k)) for k in ("json", "types", "headers"))
    spec = entry["web"]
    keys(spec, {"action", "path", "selector", "test_id", "label", "role", "name", "text", "value", "key"}, "页面步骤")
    action = spec.get("action")
    if action not in WEB_ACTIONS:
        raise ValueError(f"不支持的页面动作：{action}")
    if action in {"goto", "assert_url"} and not isinstance(spec.get("path"), str):
        raise ValueError(f"{action} 必须填写 path")
    if action in {"fill", "select", "assert_title", "assert_value"} and "value" not in spec:
        raise ValueError(f"{action} 必须填写 value")
    if action == "assert_text" and "text" not in spec:
        raise ValueError("assert_text 必须填写 text")
    if action == "press" and "key" not in spec:
        raise ValueError("press 必须填写 key")
    if action not in {"goto", "assert_url", "assert_title", "assert_text"} and sum(k in spec for k in ("selector", "test_id", "label", "role", "text")) != 1:
        raise ValueError(f"{action} 必须提供且只提供一种定位：selector/test_id/label/role/text")
    return action.startswith("assert_")


@dataclass
class CaseSpec:
    path: Path
    module: str
    module_name: str
    case: dict


def load_specs(directory):
    directory = Path(directory)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError("cases-dir 必须是目录")
    shared_path = directory / "_shared.yaml"
    shared = read_yaml(shared_path) if shared_path.exists() else {}
    keys(shared, {"variables", "flows"}, "公共配置")
    specs, seen_modules = [], set()
    paths = sorted(set(directory.rglob("*.yaml")) | set(directory.rglob("*.yml")))
    for path in paths:
        if path == shared_path or path.name.startswith("_"):
            continue
        data = read_yaml(path)
        keys(data, {"module", "name", "enabled", "variables", "flows", "cases"}, path.name)
        module = data.get("module", path.stem)
        if not isinstance(module, str) or not MODULE.fullmatch(module):
            raise ValueError(f"模块标识只能包含中文、字母、数字、下划线或短横线：{path.name}")
        if module in seen_modules:
            raise ValueError(f"模块标识重复：{module}")
        seen_modules.add(module)
        cases = data.get("cases", [])
        if not isinstance(cases, list):
            raise ValueError(f"{path.name} 的 cases 必须是列表")
        flows = {**mapping(shared.get("flows", {}), "公共 flows"), **mapping(data.get("flows", {}), "模块 flows")}
        variables = {**mapping(shared.get("variables", {}), "公共变量"), **mapping(data.get("variables", {}), "模块变量")}
        seen_ids = set()
        for original in cases:
            keys(original, {"id", "name", "type", "access", "enabled", "tags", "variables", "before", "steps", "cleanup", "request", "expect", "extract"}, f"{path.name} 用例")
            case = deepcopy(original)
            identifier = case.get("id")
            if not isinstance(identifier, str) or not MODULE.fullmatch(identifier) or identifier in seen_ids:
                raise ValueError(f"{path.name} 用例 id 必须为唯一的中文、字母、数字、下划线或短横线标识")
            seen_ids.add(identifier)
            if case.get("access", "write") not in {"readonly", "write"}:
                raise ValueError(f"{identifier} 的 access 必须为 readonly 或 write")
            tags = case.get("tags", [])
            if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
                raise ValueError(f"{identifier} 的 tags 必须为字符串列表")
            for enabled in (data.get("enabled", True), case.get("enabled", True)):
                if type(enabled) is not bool:
                    raise ValueError("enabled 必须为 true 或 false")
            case["enabled"] = data.get("enabled", True) and case.get("enabled", True)
            case["variables"] = {**variables, **mapping(case.get("variables", {}), "用例变量")}
            if "request" in case:
                if "steps" in case:
                    raise ValueError(f"{identifier} 的 request 简写与 steps 不能同时填写")
                request = dict(mapping(case["request"], "request"))
                request["expect"] = case.get("expect", {})
                request["extract"] = case.get("extract", {})
                case["steps"] = [{"api": request}]
            elif "expect" in case or "extract" in case:
                raise ValueError("用例级 expect/extract 只用于 request 简写；其他断言写在步骤内")
            for phase in ("before", "steps", "cleanup"):
                case[phase] = expand_steps(case.get(phase, []), flows)
            all_steps = case["before"] + case["steps"] + case["cleanup"]
            validations = [validate_step(s) for s in all_steps]
            if not case["steps"] or not any(validations[:len(case["before"]) + len(case["steps"])]):
                raise ValueError(f"{identifier} 必须有执行步骤，且准备或执行阶段至少包含一个断言")
            kinds = {"api" if "api" in s else "web" for s in all_steps}
            inferred = "workflow" if len(kinds) > 1 else next(iter(kinds))
            declared = case.get("type", inferred)
            if declared not in {"api", "web", "workflow"} or (inferred == "workflow" and declared != "workflow") or (declared != "workflow" and declared != inferred):
                raise ValueError(f"{identifier} 的 type 与实际步骤不一致，应使用 {inferred}")
            case["type"] = declared
            specs.append(CaseSpec(path.resolve(), module, str(data.get("name", module)), case))
    return specs


def resolve(value, variables):
    def lookup(name, stack):
        if name in stack or len(stack) > 20:
            raise ValueError(f"变量循环引用：{name}")
        if name.startswith("ENV:"):
            key = name[4:]
            if key not in os.environ:
                raise ValueError(f"缺少环境变量：{key}，请在 .env 中填写")
            return os.environ[key]
        if name not in variables:
            raise ValueError(f"变量尚未定义：{name}")
        return render(variables[name], (*stack, name))

    def render(item, stack=()):
        if isinstance(item, dict):
            return {k: render(v, stack) for k, v in item.items()}
        if isinstance(item, list):
            return [render(v, stack) for v in item]
        if not isinstance(item, str):
            return item
        match = VARIABLE.fullmatch(item)
        if match:
            return lookup(match[1], stack)
        return VARIABLE.sub(lambda m: str(lookup(m[1], stack)), item)
    return render(value)


def locator(page, spec):
    if "selector" in spec:
        return page.locator(spec["selector"])
    if "test_id" in spec:
        return page.get_by_test_id(spec["test_id"])
    if "label" in spec:
        return page.get_by_label(spec["label"], exact=True)
    if "role" in spec:
        kwargs = {"name": str(spec["name"]), "exact": True} if "name" in spec else {}
        return page.get_by_role(spec["role"], **kwargs)
    return page.get_by_text(str(spec["text"]), exact=True)


class Executor:
    def __init__(self, spec, request):
        self.spec, self.request = spec, request
        self.settings = request.getfixturevalue("settings")
        self.variables = {"uuid": uuid4().hex, "timestamp": str(time.time_ns()), **spec.case["variables"]}
        self.record = request.config._automation.case(request.node)
        self.record.setdefault("_secrets", [])
        kinds = {"api" if "api" in s else "web" for phase in ("before", "steps", "cleanup") for s in spec.case[phase]}
        self.api = request.getfixturevalue("api_client") if "api" in kinds else None
        self.page = request.getfixturevalue("page") if "web" in kinds else None
        # 先创建页面/接口资源，再创建清理夹具，确保回调执行时资源仍存活。
        request.getfixturevalue("cleanup_registry").register(self.cleanup)

    def execute(self, entries, cleanup=False):
        errors = []
        for entry in entries:
            if "when_defined" in entry and entry["when_defined"] not in self.variables:
                with step(f"跳过步骤：变量 {entry['when_defined']} 尚未产生") as record:
                    record["status"] = "skipped"
                continue
            try:
                if "api" in entry:
                    self.api_step(resolve(entry["api"], self.variables))
                else:
                    self.web_step(resolve(entry["web"], self.variables))
            except Exception as exc:
                if not cleanup:
                    raise
                errors.append(str(exc))
        if errors:
            raise RuntimeError("配置清理步骤失败：" + "；".join(errors))

    def cleanup(self):
        self.execute(self.spec.case["cleanup"], cleanup=True)

    def api_step(self, spec):
        response = self.api.request(spec.get("method", "GET"), spec["path"], **{k: v for k, v in spec.items() if k in {"json", "data", "params", "headers", "form"}})
        for name, extraction in spec.get("extract", {}).items():
            if isinstance(extraction, str):
                path, sensitive = extraction, any(word in name.lower() for word in ("token", "password", "secret", "cookie"))
            else:
                keys(extraction, {"path", "sensitive"}, "变量提取")
                path, sensitive = extraction["path"], extraction.get("sensitive", any(word in name.lower() for word in ("token", "password", "secret", "cookie")))
            value = json_value(response, path)
            self.variables[name] = value
            if sensitive and value is not None:
                self.record["_secrets"].append(str(value))
        assertion = spec.get("expect", {})
        if "status" in assertion:
            assert_status(response, assertion["status"])
        for path, expected in assertion.get("json", {}).items():
            assert_json_value(response, path, expected)
        for path, expected in assertion.get("types", {}).items():
            assert_json_type(response, path, TYPES[expected])
        if "max_ms" in assertion:
            assert_duration(self.api, assertion["max_ms"])
        if "contains" in assertion:
            with step("验证响应正文包含预期文字"):
                assert str(assertion["contains"]) in response.text(), "响应正文未包含预期文字"
        for name, expected in assertion.get("headers", {}).items():
            with step(f"验证响应头：{name}"):
                assert response.headers.get(name.lower()) == str(expected), f"响应头 {name} 不符合预期"

    def web_step(self, spec):
        action = spec["action"]
        with step("页面步骤：" + {"goto":"打开页面", "fill":"填写字段", "click":"点击", "check":"勾选", "uncheck":"取消勾选", "select":"选择选项", "press":"按键", "assert_text":"验证文字", "assert_title":"验证标题", "assert_url":"验证地址", "assert_visible":"验证元素可见", "assert_hidden":"验证元素隐藏", "assert_value":"验证字段值"}[action]):
            if action == "goto":
                self.page.goto(self.settings.resolve_url(spec["path"], "web"))
            elif action == "assert_title":
                expect(self.page).to_have_title(str(spec["value"]))
            elif action == "assert_url":
                expect(self.page).to_have_url(self.settings.resolve_url(spec["path"], "web"))
            elif action == "assert_text":
                expect(self.page.get_by_text(str(spec["text"]), exact=True)).to_be_visible()
            else:
                target = locator(self.page, spec)
                if action == "fill":
                    target.fill(str(spec["value"]))
                elif action == "click":
                    target.click()
                elif action == "check":
                    target.check()
                elif action == "uncheck":
                    target.uncheck()
                elif action == "select":
                    target.select_option(str(spec["value"]))
                elif action == "press":
                    target.press(spec["key"])
                elif action == "assert_visible":
                    expect(target).to_be_visible()
                elif action == "assert_hidden":
                    expect(target).to_be_hidden()
                elif action == "assert_value":
                    expect(target).to_have_value(str(spec["value"]))


class YamlFile(pytest.File):
    def collect(self):
        for spec in self.config._yaml_specs:
            if spec.path != self.path.resolve():
                continue
            def execute(request, spec=spec):
                runner = Executor(spec, request)
                runner.execute(spec.case["before"])
                runner.execute(spec.case["steps"])
            item = pytest.Function.from_parent(self, name=spec.case["id"], callobj=execute)
            item.add_marker(getattr(pytest.mark, spec.case["type"]))
            item.add_marker(getattr(pytest.mark, spec.case.get("access", "write")))
            item.add_marker(pytest.mark.module(spec.module))
            item.add_marker(pytest.mark.title(f"{spec.module_name} / {spec.case.get('name', spec.case['id'])}"))
            for tag in spec.case.get("tags", []):
                item.add_marker(pytest.mark.tag(tag))
            if not spec.case["enabled"]:
                item.add_marker(pytest.mark.skip(reason="模块或用例 enabled=false，尚未启用"))
            yield item


class YamlPlugin:
    def __init__(self, specs):
        self.specs = specs

    def pytest_configure(self, config):
        config._yaml_specs = self.specs

    def pytest_collect_file(self, file_path, parent):
        if any(spec.path == file_path.resolve() for spec in self.specs):
            return YamlFile.from_parent(parent, path=file_path)
