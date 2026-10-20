"""生成离线中文 HTML 与 JSON，清理框架自己创建的过期报告。"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from framework.reporting.models import STATUS_LABELS
from framework.security import redact, mask_values

MARKER = ".automation-report"


def build_report(run_result, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    secrets = [s for case in run_result.get("cases", []) for s in case.get("_secrets", [])]
    data = redact(mask_values(run_result, secrets), run_result.get("sensitive_fields", []))
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(default=True))
    html = env.get_template("report.html.j2").render(run=data, labels=STATUS_LABELS)
    for name, content in (("result.json", json.dumps(data, ensure_ascii=False, indent=2, default=str)), ("report.html", html)):
        temp = output_dir / (name + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(output_dir / name)
    (output_dir / MARKER).write_text(data["run_id"], encoding="utf-8")
    return output_dir / "report.html"


def prune_reports(root, current, days):
    root, current = Path(root).resolve(), Path(current).resolve()
    warnings = []
    now = datetime.now(timezone.utc).timestamp()
    for child in root.iterdir():
        if child.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
            continue
        if not child.is_dir() or child.resolve() == current or child.resolve().parent != root:
            continue
        marker = child / MARKER
        if not marker.is_file():
            continue
        if now - marker.stat().st_mtime <= days * 86400:
            continue
        try:
            # 删除前再次核实绝对路径和当前运行，限定为报告根目录直接子目录。
            if child.resolve().parent != root or child.resolve() == current:
                raise ValueError("报告路径越界")
            shutil.rmtree(child)
        except OSError as exc:
            warnings.append(f"历史报告清理失败：{child.name}：{exc}")
    return warnings
