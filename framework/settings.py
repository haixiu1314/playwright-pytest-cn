"""加载、校验环境配置，并统一管理地址边界。"""
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import os
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def origin(url: str) -> str:
    part = urlsplit(url)
    if part.scheme not in {"http", "https"} or not part.hostname or part.username or part.password:
        raise ValueError(f"地址必须为不含账号密码的 HTTP/HTTPS URL：{url}")
    port = part.port or (443 if part.scheme == "https" else 80)
    return f"{part.scheme}://{part.hostname.lower()}:{port}"


@dataclass
class Settings:
    root: Path
    environment: str
    project_name: str
    target: dict
    execution: dict
    report: dict

    def resolve_url(self, path: str, kind: str = "api") -> str:
        base = self.target.get(f"{kind}_base_url", "")
        if not base:
            raise ValueError(f"当前环境未配置 {kind}_base_url")
        url = urljoin(base.rstrip("/") + "/", path)
        self.check_url(url, kind)
        return url

    def check_url(self, url: str, kind: str) -> None:
        allowed = {origin(self.target[f"{kind}_base_url"])}
        allowed.update(origin(x) for x in self.target.get("allowed_origins", []))
        if origin(url) not in allowed:
            raise ValueError(f"目标地址不在当前环境允许列表中：{origin(url)}")


def load_settings(env_name=None, config_path=None) -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    path = Path(config_path).resolve() if config_path else ROOT / "config/environments.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("配置内容必须是映射")
        name = env_name or data.get("default_environment", "local")
        target = data["environments"][name]
        if not isinstance(target, dict):
            raise ValueError("环境配置必须是映射")
        for key in ("web_base_url", "api_base_url"):
            if target.get(key):
                origin(target[key])
        for item in target.get("allowed_origins", []):
            origin(item)
        for flag in ("allow_write", "verify_tls"):
            if flag in target and not isinstance(target[flag], bool):
                raise ValueError(f"{flag} 必须是布尔值")
        execution = {"browser": "chromium", "headless": True, "timeout_ms": 15000, "retries": 0, **data.get("execution", {})}
        report = {"directory": "reports", "retention_days": 7, "screenshot_on_failure": True, "trace": "retain-on-failure", **data.get("report", {})}
        if execution["browser"] not in {"chromium", "msedge"}:
            raise ValueError("第一版 browser 仅支持 chromium 或 msedge")
        if type(execution["timeout_ms"]) is not int or execution["timeout_ms"] <= 0:
            raise ValueError("timeout_ms 必须是正整数")
        if execution["retries"] != 0:
            raise ValueError("第一版不启用自动重试，retries 必须为 0")
        if report.get("trace") not in {"off", "retain-on-failure"}:
            raise ValueError("trace 仅支持 off 或 retain-on-failure")
        if type(report["retention_days"]) is not int or report["retention_days"] < 0:
            raise ValueError("retention_days 必须为非负整数")
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))
        return Settings(ROOT, name, str(data.get("project_name", "通用自动化测试")), target, execution, report)
    except (OSError, KeyError, TypeError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"读取配置失败：{exc}") from exc
