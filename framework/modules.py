"""模块目录与模板；列出 Python 文件时只读取 AST，不导入业务代码。"""
import ast
from pathlib import Path
import yaml
from framework.declarative import MODULE


def inventory(specs, tests):
    result = {}
    for spec in specs:
        entry = result.setdefault(spec.module, {"name": spec.module_name, "yaml": 0, "python": 0})
        entry["yaml"] += 1
    tests = Path(tests)
    paths = [tests] if tests.is_file() else sorted(tests.rglob("test_*.py")) if tests.exists() else []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
                continue
            module = path.stem.removeprefix("test_")
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "module" and decorator.args and isinstance(decorator.args[0], ast.Constant):
                    module = str(decorator.args[0].value)
            entry = result.setdefault(module, {"name": module, "yaml": 0, "python": 0})
            entry["python"] += 1
    return result


def scaffold(directory, module):
    if not MODULE.fullmatch(module):
        raise ValueError("模块标识只能包含中文、字母、数字、下划线或短横线")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{module}.yaml"
    data = {"module": module, "name": module, "enabled": False, "variables": {}, "cases": [
        {"id": "api_check", "name": "接口检查（请替换路径及断言）", "access": "readonly", "tags": ["smoke"], "request": {"method": "GET", "path": "/replace-me"}, "expect": {"status": 200, "json": {"code": 0}}},
        {"id": "web_check", "name": "页面检查（请替换路径及标题）", "access": "readonly", "tags": ["smoke"], "steps": [{"web": {"action": "goto", "path": "/replace-me"}}, {"web": {"action": "assert_title", "value": "请填写实际页面标题"}}]}
    ]}
    try:
        with path.open("x", encoding="utf-8") as output:
            output.write("# 填写真实路径和断言后，将 enabled 改为 true。无需重复填写域名。\n")
            yaml.safe_dump(data, output, allow_unicode=True, sort_keys=False)
    except FileExistsError as exc:
        raise ValueError(f"模块文件已存在，未覆盖：{path}") from exc
    return path
