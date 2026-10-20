"""平台业务服务：文件校验、原子保存、独立执行进程与持久化任务。"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, RLock, Thread
from uuid import uuid4
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import yaml
from framework.declarative import MODULE, load_specs, read_yaml
from framework.modules import inventory
from framework.security import redact
from framework.settings import ROOT, load_settings, origin
from test_platform.store import Store, now


class Conflict(ValueError):
    pass


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


class Platform:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.config_path = self.root / "config/environments.yaml"
        self.case_dir = self.root / "cases"
        self.data_dir = self.root / ".platform"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock_file = (self.data_dir / "platform.lock").open("a+b")
        self._lock_file.write(b"0")
        self._lock_file.flush()
        self._lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._lock_file.close()
            raise ValueError("此工作空间已有测试平台运行，请使用已打开的平台") from exc
        self.store = Store(self.data_dir / "history.sqlite3")
        self.lock = RLock()
        self.active = None
        self.process = None
        self.worker = None
        self.cancel = Event()

    def configuration(self):
        text = self.config_path.read_text(encoding="utf-8-sig")
        data = yaml.safe_load(text)
        if not isinstance(data, dict) or not isinstance(data.get("environments"), dict):
            raise ValueError("环境配置格式不正确")
        return {"data": data, "revision": digest(text)}

    def save_configuration(self, payload):
        with self.lock:
            self.ensure_idle()
            current = self.configuration()
            if payload.get("revision") != current["revision"]:
                raise Conflict("配置已被修改，请刷新页面后重试")
            data = deepcopy(current["data"])
            environments = payload.get("environments")
            if not isinstance(environments, dict) or not environments:
                raise ValueError("至少需要一个环境")
            for name, target in environments.items():
                if not isinstance(name, str) or not MODULE.fullmatch(name) or not isinstance(target, dict):
                    raise ValueError("环境名称或配置不正确")
                for key in ("web_base_url", "api_base_url"):
                    if target.get(key):
                        origin(target[key])
                if not isinstance(target.get("allowed_origins", []), list):
                    raise ValueError("allowed_origins 必须是列表")
                for value in target.get("allowed_origins", []):
                    origin(value)
                for flag in ("allow_write", "verify_tls"):
                    if type(target.get(flag, flag == "verify_tls")) is not bool:
                        raise ValueError(f"{flag} 必须为布尔值")
            data["environments"] = environments
            data["default_environment"] = payload.get("default_environment")
            if data["default_environment"] not in environments:
                raise ValueError("默认环境必须存在")
            text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            with TemporaryDirectory(dir=self.data_dir, prefix="validate-") as temp:
                check = Path(temp) / "config.yaml"
                check.write_text(text, encoding="utf-8")
                for name in environments:
                    load_settings(name, check)
            atomic(self.config_path, text)
            return self.configuration()

    def module_path(self, filename):
        if not isinstance(filename, str) or not filename or "\\" in filename:
            raise ValueError("模块文件名无效")
        path = (self.case_dir / filename).resolve()
        if not path.is_relative_to(self.case_dir.resolve()) or path.suffix not in {".yaml", ".yml"}:
            raise ValueError("模块文件超出用例目录")
        if any(part.startswith(".") for part in Path(filename).parts):
            raise ValueError("模块路径无效")
        return path

    def module(self, filename):
        path = self.module_path(filename)
        if not path.is_file():
            raise ValueError("模块文件不存在")
        text = path.read_text(encoding="utf-8-sig")
        return {"file": filename, "text": text, "data": yaml.safe_load(text) or {}, "revision": digest(text)}

    def modules(self):
        specs = load_specs(self.case_dir)
        found = inventory(specs, self.root / "tests")
        rows = []
        files = sorted(set(self.case_dir.rglob("*.yaml")) | set(self.case_dir.rglob("*.yml"))) if self.case_dir.exists() else []
        for path in files:
            if path.name.startswith("_"):
                continue
            data = read_yaml(path)
            module = data.get("module", path.stem)
            matching = [s for s in specs if s.path == path.resolve()]
            rows.append({"id": module, "name": str(data.get("name", module)), "file": path.relative_to(self.case_dir).as_posix(), "source": "yaml", "enabled": data.get("enabled", True), "count": len(matching), "api": sum(s.case["type"] == "api" for s in matching), "web": sum(s.case["type"] == "web" for s in matching), "workflow": sum(s.case["type"] == "workflow" for s in matching), "cases": [{"id": s.case["id"], "name": s.case.get("name", s.case["id"]), "type": s.case["type"], "enabled": s.case["enabled"], "tags": s.case.get("tags", [])} for s in matching]})
        for module, value in found.items():
            if value["python"]:
                rows.append({"id": module, "name": value["name"], "source": "python", "enabled": True, "count": value["python"], "cases": []})
        return rows

    def save_module(self, payload):
        with self.lock:
            self.ensure_idle()
            filename = payload.get("file")
            path = self.module_path(filename)
            if filename.startswith("_") and filename != "_shared.yaml":
                raise ValueError("保留下划线开头的文件仅允许 _shared.yaml")
            if path.exists():
                current = self.module(filename)
                if payload.get("revision") != current["revision"]:
                    raise Conflict("模块已被修改，请重新打开后编辑")
            elif payload.get("revision"):
                raise Conflict("模块已被其他操作移除，请刷新")
            data = payload.get("data")
            text = payload.get("text")
            if text is not None:
                if not isinstance(text, str):
                    raise ValueError("配置内容必须是文本")
                data = yaml.safe_load(text)
            else:
                text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            if not isinstance(data, dict):
                raise ValueError("模块内容必须为对象")
            if filename != "_shared.yaml":
                module = data.get("module", path.stem)
                if not isinstance(module, str) or not MODULE.fullmatch(module) or module.startswith("_"):
                    raise ValueError("模块标识只支持中文、字母、数字、下划线和短横线，不能以下划线开头")
            with TemporaryDirectory(dir=self.data_dir, prefix="validate-") as temp:
                temporary = Path(temp)
                for existing in self.case_dir.rglob("*"):
                    if existing.is_file() and existing.suffix in {".yaml", ".yml"}:
                        relative = existing.relative_to(self.case_dir)
                        dest = temporary / relative
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(existing.read_bytes())
                candidate = temporary / filename
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text(text, encoding="utf-8")
                load_specs(temporary)
            atomic(path, text)
            return self.module(filename)

    def delete_module(self, payload):
        with self.lock:
            self.ensure_idle()
            filename = payload.get("file")
            if filename == "_shared.yaml":
                raise ValueError("公共流程不能删除，可以编辑其内容")
            current = self.module(filename)
            if payload.get("revision") != current["revision"]:
                raise Conflict("模块已被修改，请刷新")
            self.module_path(filename).unlink()
            return {"deleted": True}

    def ensure_idle(self):
        if self.active:
            raise Conflict("当前有任务正在执行，请完成或停止后再修改或启动")

    def report_root(self):
        config = self.configuration()["data"]
        path = Path(config.get("report", {}).get("directory", "reports"))
        return (path if path.is_absolute() else self.root / path).resolve()

    def reports(self):
        root = self.report_root()
        rows = []
        if not root.exists():
            return rows
        for directory in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
            if not directory.is_dir() or directory.is_symlink() or not (directory / ".automation-report").is_file():
                continue
            try:
                result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
                rows.append({"id": directory.name, "environment": result.get("environment"), "started_at": result.get("started_at"), "summary": result.get("summary", {}), "exit_code": result.get("exit_code"), "pass_rate": result.get("pass_rate"), "url": f"/reports/{directory.name}/report.html"})
            except (OSError, ValueError):
                continue
            if len(rows) >= 100:
                break
        return rows

    def start(self, payload):
        with self.lock:
            self.ensure_idle()
            config = self.configuration()["data"]
            env = payload.get("environment")
            if env not in config["environments"]:
                raise ValueError("请选择有效环境")
            scope = payload.get("scope", "all")
            if scope not in {"all", "api", "web", "workflows"}:
                raise ValueError("测试范围无效")
            modules = payload.get("modules")
            if not isinstance(modules, list) or not modules or not all(isinstance(x, str) for x in modules):
                raise ValueError("请至少选择一个模块")
            available = {row["id"] for row in self.modules()}
            if set(modules) - available:
                raise ValueError("部分模块已不存在，请刷新页面")
            for key in ("headed", "read_only", "allow_write"):
                if type(payload.get(key, False)) is not bool:
                    raise ValueError(f"{key} 必须为布尔值")
            if payload.get("allow_write") and payload.get("read_only"):
                raise ValueError("只读和允许线上写入不能同时选择")
            if payload.get("allow_write") and not config["environments"][env].get("allow_write", False):
                raise ValueError("环境尚未允许写入，请先在环境配置中设置")
            tags = payload.get("tags", "")
            if not isinstance(tags, str) or len(tags) > 500:
                raise ValueError("标签格式不正确")
            settings = load_settings(env, self.config_path)
            identifier = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
            clean = {"environment": env, "scope": scope, "modules": list(dict.fromkeys(modules)), "tags": tags, **{key: payload.get(key, False) for key in ("headed", "read_only", "allow_write")}}
            self.store.create(identifier, clean)
            self.active = identifier
            self.cancel.clear()
            report_root = self.report_root()
            self.worker = Thread(target=self.execute, args=(identifier, clean, report_root), daemon=True)
            self.worker.start()
            return {"id": identifier}

    def execute(self, identifier, payload, report_root):
        log, report_id = "", None
        process = None
        try:
            before = {p.name for p in report_root.iterdir()} if report_root.exists() else set()
            args = [sys.executable, "-B", "-u", "-m", "framework.cli", "--config", str(self.config_path), "--tests", str(self.root / "tests"), "--case-dir", str(self.case_dir), "--report-dir", str(report_root), "--env", payload["environment"], "--scope", payload["scope"], "--module", ",".join(payload["modules"])]
            if payload["tags"]:
                args += ["--tag", payload["tags"]]
            for flag in ("headed", "read_only", "allow_write"):
                if payload[flag]:
                    args.append("--" + flag.replace("_", "-"))
            self.store.update(identifier, status="running")
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
            kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **kwargs)
            with self.lock:
                self.process = process
            if self.cancel.is_set():
                self.schedule_stop(process)
            for line in process.stdout:
                log = (log + redact(line))[-1000000:]
                self.store.update(identifier, log=log)
            code = process.wait()
            result = None
            if report_root.exists():
                for directory in sorted(report_root.iterdir(), key=lambda p: p.name, reverse=True):
                    if directory.name in before or not (directory / ".automation-report").is_file():
                        continue
                    if (directory / "result.json").exists():
                        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
                        report_id = directory.name
                        break
            if self.cancel.is_set():
                status = "cancelled"
            elif code == 5:
                status = "no_tests"
            elif code != 0:
                status = "failed" if code == 1 else "error"
            elif not result:
                status = "error"
            elif not sum(result.get("summary", {}).get(k, 0) for k in ("passed", "failed", "error")):
                status = "skipped"
            else:
                status = "passed"
            self.store.update(identifier, status=status, exit_code=code, report_id=report_id, result=json.dumps(result, ensure_ascii=False) if result else None, finished=now())
        except Exception as exc:
            self.store.update(identifier, status="cancelled" if self.cancel.is_set() else "error", log=(log + "\n平台执行异常：" + redact(str(exc)))[-1000000:], finished=now())
        finally:
            if process is not None:
                if process.poll() is None:
                    self.hard_stop(process)
                if process.stdout:
                    process.stdout.close()
            with self.lock:
                self.active, self.process = None, None

    def signal_stop(self, process):
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(process.pid, signal.SIGINT)
        except OSError:
            process.terminate()

    def hard_stop(self, process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

    def stop(self, identifier):
        with self.lock:
            if self.active != identifier:
                raise Conflict("任务已结束，不能停止")
            self.cancel.set()
            self.store.update(identifier, status="stopping")
            process = self.process
            if process:
                self.schedule_stop(process)
            return {"status": "stopping"}

    def schedule_stop(self, process):
        self.signal_stop(process)
        def fallback():
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.hard_stop(process)
        Thread(target=fallback, daemon=True).start()

    def close(self):
        if self.active:
            self.stop(self.active)
        if self.worker:
            self.worker.join(timeout=18)
        if not self._lock_file.closed:
            self._lock_file.close()
