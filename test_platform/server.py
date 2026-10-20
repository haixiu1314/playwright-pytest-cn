"""仅本机访问的 HTTP 服务，提供平台页面、JSON API 和报告资源。"""
import argparse
import hmac
import json
import mimetypes
from pathlib import Path
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
import webbrowser
import yaml
from framework.security import redact
from framework.settings import ROOT
from test_platform.service import Platform, Conflict

STATIC = Path(__file__).parent / "static"


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, app):
        self.app = app
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "TestPlatform/2.0"

    def log_message(self, *args):
        pass

    def respond(self, status, data, kind="application/json; charset=utf-8", report=False):
        content = json.dumps(data, ensure_ascii=False).encode("utf-8") if kind.startswith("application/json") and not isinstance(data, bytes) else data
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        policy = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
        if report:
            policy = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'self'"
        self.send_header("Content-Security-Policy", policy)
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def check_origin(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed:
            raise PermissionError("平台只允许本机地址访问")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{value}" for value in allowed}:
            raise PermissionError("请求来源与平台不一致")
        if self.command != "GET" and not hmac.compare_digest(self.headers.get("X-Platform-Token", ""), self.server.token):
            raise PermissionError("页面会话失效，请刷新后重试")

    def body(self):
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            raise ValueError("请求必须使用 JSON")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 2 * 1024 * 1024:
            raise ValueError("请求内容应在 2 MB 以内")
        result = json.loads(self.rfile.read(length))
        if not isinstance(result, dict):
            raise ValueError("请求内容必须为对象")
        return result

    def dispatch(self):
        self.check_origin()
        app = self.server.app
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        if self.command == "GET":
            if path == "/api/bootstrap":
                try:
                    modules, error = app.modules(), ""
                except (ValueError, SyntaxError) as exc:
                    modules, error = [], str(exc)
                return self.respond(200, {"version": "2.0", "token": self.server.token, "config": app.configuration(), "modules": modules, "module_error": error, "active": app.active})
            if path == "/api/runs":
                return self.respond(200, {"runs": app.store.list(), "active": app.active})
            if path.startswith("/api/runs/"):
                return self.respond(200, app.store.get(path.rsplit("/", 1)[-1]))
            if path == "/api/reports":
                return self.respond(200, app.reports())
            if path == "/api/module":
                return self.respond(200, app.module(query.get("file", [""])[0]))
            if path.startswith("/reports/"):
                relative = Path(path[len("/reports/"):])
                root = app.report_root()
                candidate = (root / relative).resolve()
                if len(relative.parts) < 2 or not candidate.is_relative_to(root) or not (root / relative.parts[0] / ".automation-report").is_file():
                    raise PermissionError("报告路径无效")
                types = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".png": "image/png", ".zip": "application/zip"}
                if candidate.suffix not in types or not candidate.is_file():
                    return self.respond(404, {"error": "报告或附件已被清理"})
                return self.respond(200, candidate.read_bytes(), types[candidate.suffix], report=True)
            files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path in files:
                name, kind = files[path]
                return self.respond(200, (STATIC / name).read_bytes(), kind)
        elif self.command in {"POST", "PUT", "DELETE"}:
            payload = self.body()
            if path == "/api/config" and self.command == "PUT":
                return self.respond(200, app.save_configuration(payload))
            if path == "/api/module" and self.command == "PUT":
                return self.respond(200, app.save_module(payload))
            if path == "/api/module" and self.command == "DELETE":
                return self.respond(200, app.delete_module(payload))
            if path == "/api/runs" and self.command == "POST":
                return self.respond(202, app.start(payload))
            if path.startswith("/api/runs/") and path.endswith("/stop") and self.command == "POST":
                return self.respond(200, app.stop(path.split("/")[-2]))
        return self.respond(404, {"error": "页面或接口不存在"})

    def handle_request(self):
        try:
            self.dispatch()
        except Conflict as exc:
            self.respond(409, {"error": str(exc)})
        except PermissionError as exc:
            self.respond(403, {"error": str(exc)})
        except (ValueError, TypeError, KeyError, SyntaxError, yaml.YAMLError) as exc:
            self.respond(400, {"error": redact(str(exc))})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except OSError as exc:
            self.respond(500, {"error": "文件或进程操作失败：" + redact(str(exc))})
        except Exception:
            self.respond(500, {"error": "平台内部错误，请查看控制台并重启平台"})

    do_GET = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_DELETE = handle_request


def main():
    parser = argparse.ArgumentParser(description="中文自动化测试平台")
    parser.add_argument("--port", type=int, default=8765, help="本机端口，默认 8765")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    options = parser.parse_args()
    if not 1 <= options.port <= 65535:
        parser.error("端口必须在 1 到 65535 之间")
    try:
        app = Platform()
    except (ValueError, OSError) as exc:
        print(f"平台启动失败：{exc}")
        return 1
    try:
        server = Server(("127.0.0.1", options.port), app)
    except OSError as exc:
        app.close()
        print(f"平台启动失败：端口 {options.port} 可能被占用。可通过 --port 指定其他端口。{exc}")
        return 1
    url = f"http://127.0.0.1:{options.port}"
    print(f"中文测试平台已启动：{url}\n保留此窗口运行；按 Ctrl+C 关闭平台。", flush=True)
    if not options.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\n正在关闭平台与运行中的任务……", flush=True)
    finally:
        app.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
