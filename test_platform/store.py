"""SQLite 只保存平台执行历史；业务用例和环境继续保存在原文件中。"""
from contextlib import contextmanager
from datetime import datetime
import json
import sqlite3


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT, finished TEXT, status TEXT, payload TEXT, log TEXT DEFAULT '', exit_code INTEGER, report_id TEXT, result TEXT)")
            db.execute("UPDATE runs SET status='interrupted', finished=? WHERE status IN ('queued','running','stopping')", (now(),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def create(self, identifier, payload):
        with self.connect() as db:
            db.execute("INSERT INTO runs(id,created,status,payload) VALUES(?,?,?,?)", (identifier, now(), "queued", json.dumps(payload, ensure_ascii=False)))

    def update(self, identifier, **fields):
        allowed = {"status", "log", "exit_code", "finished", "report_id", "result"}
        if not fields or not set(fields) <= allowed:
            raise ValueError("无效的任务更新")
        with self.connect() as db:
            db.execute("UPDATE runs SET " + ",".join(f"{key}=?" for key in fields) + " WHERE id=?", (*fields.values(), identifier))

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("执行记录不存在")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def list(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,created,finished,status,payload,exit_code,report_id FROM runs ORDER BY created DESC,rowid DESC LIMIT 100").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]
