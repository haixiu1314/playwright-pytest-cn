"""框架夹具：配置、请求上下文、浏览器和资源清理。"""
import os
import pytest
from playwright.sync_api import sync_playwright, expect
from framework.api_client import ApiClient
from framework.lifecycle import CleanupRegistry
from framework.browser import launch_options


@pytest.fixture(scope="session")
def settings(pytestconfig):
    return pytestconfig._automation.settings


@pytest.fixture(scope="session")
def playwright_runtime():
    with sync_playwright() as runtime:
        yield runtime


@pytest.fixture
def api_client(playwright_runtime, settings, pytestconfig):
    headers = {}
    if os.getenv("AUTOMATION_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["AUTOMATION_TOKEN"]
    state = os.getenv("AUTOMATION_STORAGE_STATE") or None
    context = playwright_runtime.request.new_context(extra_http_headers=headers, storage_state=state, ignore_https_errors=not settings.target.get("verify_tls", True), timeout=settings.execution["timeout_ms"])
    try:
        yield ApiClient(context, settings, pytestconfig._automation.policy_readonly)
    finally:
        context.dispose()


@pytest.fixture
def page(playwright_runtime, settings, request, pytestconfig):
    reporter = pytestconfig._automation
    launch = launch_options(settings, reporter.options.headed)
    browser = playwright_runtime.chromium.launch(**launch)
    context = None
    try:
        context = browser.new_context(ignore_https_errors=not settings.target.get("verify_tls", True), storage_state=os.getenv("AUTOMATION_STORAGE_STATE") or None, service_workers="block")
        context.set_default_timeout(settings.execution["timeout_ms"])
        expect.set_options(timeout=settings.execution["timeout_ms"])

        def guard(route):
            url = route.request.url
            if url.startswith(("data:", "blob:", "about:")):
                route.continue_()
                return
            try:
                settings.check_url(url, "web")
                if reporter.policy_readonly and route.request.method not in {"GET", "HEAD", "OPTIONS"}:
                    raise ValueError("只读模式禁止页面发送写入请求")
            except ValueError as exc:
                request.node._automation_guard_errors = getattr(request.node, "_automation_guard_errors", []) + [str(exc)]
                route.abort("blockedbyclient")
                return
            route.continue_()

        # 所有页面和弹窗共用上下文路由；禁止 Service Worker 绕开路由。
        context.route("**/*", guard)
        trace_enabled = settings.report.get("trace") == "retain-on-failure"
        if trace_enabled:
            context.tracing.start(screenshots=True, snapshots=True, sources=True)
        active_page = context.new_page()
        request.node._automation_page = active_page
        yield active_page
        guard_errors = getattr(request.node, "_automation_guard_errors", [])
        if guard_errors:
            request.node._automation_failed = True
            reporter.capture(request.node)
            raise RuntimeError("浏览器请求被环境边界规则阻止：" + "；".join(dict.fromkeys(guard_errors)))
    finally:
        try:
            if context is not None:
                try:
                    if settings.report.get("trace") == "retain-on-failure":
                        if getattr(request.node, "_automation_failed", False):
                            reporter.capture(request.node)
                            path = reporter.artifact(request.node, ".zip")
                            context.tracing.stop(path=str(path))
                            reporter.case(request.node)["attachments"].append({"title": "失败 Trace（使用 Playwright 打开）", "kind": "trace", "path": path.relative_to(reporter.output_dir).as_posix()})
                        else:
                            context.tracing.stop()
                finally:
                    context.close()
        finally:
            # 即使 Trace 保存或上下文释放失败，也尝试关闭本用例浏览器。
            browser.close()


@pytest.fixture
def cleanup_registry(request, pytestconfig):
    registry = CleanupRegistry()
    yield registry
    try:
        registry.close()
    except Exception:
        request.node._automation_failed = True
        pytestconfig._automation.capture(request.node)
        raise
