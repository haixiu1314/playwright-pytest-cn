"""日志脱敏。截图和 Trace 仍需使用无真实敏感数据的测试账号。"""
import os
import re
from urllib.parse import urlsplit, urlunsplit

FIELDS = {"password", "passwd", "token", "secret", "authorization", "cookie", "set-cookie", "access_token", "refresh_token"}


def redact(value, extra=()):
    sensitive = FIELDS | {str(x).lower() for x in extra}
    if isinstance(value, dict):
        return {str(k): "***" if str(k).lower() in sensitive else redact(v, extra) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(x, extra) for x in value]
    if isinstance(value, str):
        text = value
        for key in ("AUTOMATION_TOKEN", "AUTOMATION_PASSWORD", "AUTOMATION_USERNAME"):
            secret = os.getenv(key)
            if secret:
                text = text.replace(secret, "***")
        text = re.sub(r"(?i)(Bearer\s+)[^\s\"',;]+", r"\1***", text)
        fields = "|".join(re.escape(x) for x in sensitive)
        text = re.sub(rf"(?i)((?:{fields})[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;}}]+", r"\1***", text)
        return text
    return value


def mask_values(value, secrets):
    """隐藏动态提取的密钥，并移除仅用于运行时的内部字段。"""
    if isinstance(value, dict):
        return {k: mask_values(v, secrets) for k, v in value.items() if k != "_secrets"}
    if isinstance(value, (list, tuple)):
        return [mask_values(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in sorted(set(secrets), key=len, reverse=True):
            if secret:
                value = value.replace(secret, "***")
    return value


def safe_url(url):
    part = urlsplit(url)
    # URL 查询串可能有自定义密钥，日志统一隐藏整个查询串。
    return urlunsplit((part.scheme, part.netloc, part.path, "已隐藏" if part.query else "", ""))
