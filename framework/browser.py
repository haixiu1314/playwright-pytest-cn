"""浏览器启动参数，兼容系统级安装的 Edge。"""
from pathlib import Path
import os


def launch_options(settings, headed=False):
    options = {"headless": not headed and settings.execution.get("headless", True)}
    if settings.execution["browser"] == "msedge":
        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        path = next((x for x in candidates if x.is_file()), None)
        if path is None:
            raise RuntimeError("未找到本机 Edge，请安装 Chromium 或确认 Edge 安装路径")
        options["executable_path"] = str(path)
    return options
