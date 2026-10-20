"""将 Pytest 的准备、主体、清理阶段合并为一条中文结果。"""
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import hashlib
import socket
import ssl
from urllib.parse import urlsplit
import pytest
from framework.steps import current_case
from framework.security import redact, safe_url, mask_values
from framework.reporting.models import new_case, final_status, STATUS_LABELS
from framework.reporting.builder import build_report, prune_reports


class Reporter:
    def __init__(self, settings, options):
        self.settings, self.options = settings, options
        self.run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        root = Path(options.report_dir or settings.report["directory"])
        self.report_root = root if root.is_absolute() else settings.root / root
        self.output_dir = self.report_root / self.run_id
        self.started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        self.start = perf_counter()
        self.cases, self.session_errors = {}, []
        self.policy_readonly = options.read_only or not settings.target.get("allow_write", False)
        if settings.environment == "production" and not options.allow_write:
            self.policy_readonly = True

    def say(self, text):
        secrets = [s for case in self.cases.values() for s in case.get("_secrets", [])]
        print(redact(mask_values(text, secrets), self.settings.report.get("sensitive_fields", [])), flush=True)

    def pytest_configure(self, config):
        config._automation = self
        self.config = config
        self.say(f"目标环境：{self.settings.environment}\n执行范围：{self.options.scope}\n运行编号：{self.run_id}")

    def case(self, item):
        title = item.get_closest_marker("title")
        title = str(title.args[0]) if title and title.args else item.name
        return self.cases.setdefault(item.nodeid, new_case(item.nodeid, title))

    def preflight(self, kinds):
        checked = set()
        for kind in kinds:
            url = self.settings.target.get(f"{kind}_base_url")
            if not url:
                raise pytest.UsageError(f"未配置 {kind}_base_url")
            part = urlsplit(url)
            key = (part.hostname, part.port or (443 if part.scheme == "https" else 80), part.scheme)
            if key in checked:
                continue
            checked.add(key)
            try:
                with socket.create_connection(key[:2], timeout=min(self.settings.execution["timeout_ms"] / 1000, 10)) as sock:
                    if part.scheme == "https":
                        context = ssl.create_default_context()
                        if not self.settings.target.get("verify_tls", True):
                            context.check_hostname = False
                            context.verify_mode = ssl.CERT_NONE
                        with context.wrap_socket(sock, server_hostname=part.hostname):
                            pass
            except OSError as exc:
                message = f"目标服务连通性检查失败：{safe_url(url)}；请确认服务已启动、端口及证书正确。{exc}"
                self.session_errors.append(message)
                raise pytest.UsageError(message) from exc

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items):
        selected, deselected, kinds = [], [], set()
        for item in items:
            marker = item.get_closest_marker("module")
            module = str(marker.args[0]) if marker and marker.args else item.path.stem.removeprefix("test_")
            tags = {str(m.args[0]) for m in item.iter_markers("tag") if m.args}
            if (self.options.modules and module not in self.options.modules) or (self.options.tags and not tags.intersection(self.options.tags)):
                deselected.append(item)
                continue
            parts = set(Path(str(item.path)).parts)
            scopes = {x for x in ("api", "web", "workflow") if item.get_closest_marker(x)}
            if not scopes:
                scopes = {"workflow" if "workflows" in parts else "api" if "api" in parts else "web" if "web" in parts else "unknown"}
            wanted = {"workflows": "workflow"}.get(self.options.scope, self.options.scope)
            if wanted != "all" and wanted not in scopes:
                deselected.append(item)
                continue
            if item.get_closest_marker("readonly") and item.get_closest_marker("write"):
                raise pytest.UsageError(f"用例不能同时标记 readonly 与 write：{item.nodeid}")
            blocked = self.policy_readonly and (not item.get_closest_marker("readonly") or item.get_closest_marker("write"))
            if blocked:
                item.add_marker(pytest.mark.skip(reason="当前环境只允许显式标记 readonly 的只读用例"))
            elif not item.get_closest_marker("skip"):
                if "api" in scopes or "workflow" in scopes:
                    kinds.add("api")
                if "web" in scopes or "workflow" in scopes:
                    kinds.add("web")
            self.case(item).update(module=module, tags=sorted(tags))
            selected.append(item)
        items[:] = selected
        config.hook.pytest_deselected(items=deselected)
        self.say(f"已收集：{len(selected)} 条用例（范围外 {len(deselected)} 条）")
        if selected:
            self.preflight(kinds)

    def pytest_deselected(self, items):
        for item in items:
            self.cases.pop(item.nodeid, None)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item):
        current_case.set(self.case(item))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        case = self.case(item)
        phase = {"phase": report.when, "outcome": report.outcome, "duration_ms": round(report.duration * 1000, 2), "error": str(report.longrepr) if report.longrepr else "", "wasxfail": str(getattr(report, "wasxfail", ""))}
        case["phase_results"].append(phase)
        if report.failed and report.when != "teardown":
            item._automation_failed = True
            self.capture(item)
        if report.when == "teardown":
            case["status"] = final_status(case["phase_results"])
            case["duration_ms"] = round(sum(x["duration_ms"] for x in case["phase_results"]), 2)
            case["error"] = "\n\n".join(x["error"] for x in case["phase_results"] if x["error"])
            self.say(f"[{STATUS_LABELS[case['status']]}] {case['title']}（{case['duration_ms']} 毫秒）")
            if case["status"] in {"failed", "error"}:
                self.say("  原因：" + case["error"][-1600:])
            current_case.set(None)

    def artifact(self, item, suffix):
        folder = self.output_dir / "attachments"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / (hashlib.sha256(item.nodeid.encode()).hexdigest()[:16] + suffix)

    def capture(self, item):
        page = getattr(item, "_automation_page", None)
        case = self.case(item)
        if page is None or not self.settings.report.get("screenshot_on_failure", True) or any(a["kind"] == "image" for a in case["attachments"]):
            return
        try:
            path = self.artifact(item, ".png")
            page.screenshot(path=str(path), full_page=True, timeout=5000)
            case["attachments"].append({"title": "失败截图", "kind": "image", "path": path.relative_to(self.output_dir).as_posix()})
        except Exception as exc:
            case["steps"].append({"title": "失败截图采集", "status": "failed", "duration_ms": 0, "error": str(exc)})

    def pytest_collectreport(self, report):
        if report.failed:
            self.session_errors.append("用例收集失败：\n" + str(report.longrepr))

    def pytest_keyboard_interrupt(self, excinfo):
        self.session_errors.append("执行被中断，结果可能不完整。")

    def pytest_internalerror(self, excrepr, excinfo):
        self.session_errors.append("执行框架内部错误：\n" + str(excrepr))

    def pytest_sessionfinish(self, session, exitstatus):
        for case in self.cases.values():
            if not any(p["phase"] == "teardown" for p in case["phase_results"]):
                case["status"] = "error"
                case["error"] = "用例未完整执行，请查看会话错误或中断信息。"
        summary = {key: sum(x["status"] == key for x in self.cases.values()) for key in STATUS_LABELS}
        denominator = summary["passed"] + summary["failed"] + summary["error"]
        notice = "" if denominator else "未实际验证业务：没有可统计的普通通过、失败或错误结果。"
        if not self.cases:
            notice = "未发现可执行用例；请按学习文档添加真实业务用例。"
        if exitstatus != 0:
            notice = (notice + " 本次运行未成功完成，请结合退出码及错误明细判断。 ").strip()
        run = {"run_id": self.run_id, "project_name": self.settings.project_name, "environment": self.settings.environment, "targets": {"web": safe_url(self.settings.target.get("web_base_url", "")), "api": safe_url(self.settings.target.get("api_base_url", ""))}, "started_at": self.started_at, "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"), "duration_ms": round((perf_counter() - self.start) * 1000, 2), "exit_code": int(exitstatus), "summary": summary, "pass_rate": f"{summary['passed'] / denominator:.1%}" if denominator else "无可统计结果", "notice": notice, "cases": list(self.cases.values()), "session_errors": self.session_errors, "sensitive_fields": self.settings.report.get("sensitive_fields", [])}
        try:
            report = build_report(run, self.output_dir)
            self.say("执行完成：" + "，".join(f"{STATUS_LABELS[k]} {v} 条" for k, v in summary.items()))
            if notice:
                self.say(notice)
            self.say(f"中文报告：{report}\n结构化结果：{self.output_dir / 'result.json'}")
            for warning in prune_reports(self.report_root, self.output_dir, self.settings.report["retention_days"]):
                self.say(warning)
        except Exception as exc:
            self.say(f"报告生成或历史清理失败：{exc}")
            session.exitstatus = 3
