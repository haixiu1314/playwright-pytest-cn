"""使用 Playwright 请求上下文发送接口请求，不启动浏览器。"""
from time import perf_counter
from framework.steps import step
from framework.security import redact, safe_url


def bounded(value):
    if isinstance(value, dict):
        return {str(k): bounded(v) for k, v in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [bounded(v) for v in value[:50]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…（内容已截断）"
    if isinstance(value, bytes):
        return f"二进制内容（{len(value)} 字节，不记录正文）"
    return value


class ApiClient:
    def __init__(self, context, settings, readonly=False):
        self.context = context
        self.settings = settings
        self.readonly = readonly
        self.last_duration_ms = 0.0

    def request(self, method, path, **kwargs):
        method = method.upper()
        if self.readonly and method not in {"GET", "HEAD", "OPTIONS"}:
            raise ValueError("当前为只读模式，禁止发送写入请求")
        url = self.settings.resolve_url(path, "api")
        # 禁止自动重定向，防止携带认证信息跨环境发送。
        if kwargs.get("max_redirects", 0) != 0:
            raise ValueError("接口请求禁用自动重定向；请显式检查 Location 后单独请求")
        kwargs["max_redirects"] = 0
        if "json" in kwargs:
            kwargs["data"] = kwargs.pop("json")
        with step(f"接口请求：{method} {safe_url(url)}") as record:
            start = perf_counter()
            response = self.context.fetch(url, method=method, **kwargs)
            self.last_duration_ms = round((perf_counter() - start) * 1000, 2)
            record["response"] = {"status": response.status, "duration_ms": self.last_duration_ms}
            record["request"] = bounded(redact({"headers": kwargs.get("headers", {}), "data": kwargs.get("data"), "params": kwargs.get("params")}, self.settings.report.get("sensitive_fields", [])))
            return response

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def put(self, path, **kwargs):
        return self.request("PUT", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)
