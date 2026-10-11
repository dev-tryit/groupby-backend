"""서비스 제공사 프로그램의 HTTP 진입점. 읽기 API 3개와 화면의 정적 파일을 준다 (07_api/request-response)."""
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from groupby.server.viewing.service import NotFound, ViewResults
from groupby.shared.log import log, trace_id_or_new

POSTING_PATH = re.compile(r"/api/postings/([^/]+)")
RESUME_PATH = re.compile(r"/api/resumes/([^/]+)")
POSTING_ID = re.compile(r"[0-9]+")
RESUME_ID = re.compile(r"[A-Za-z0-9_-]+")
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


class BadRequest(Exception):
    pass


def answer(view: ViewResults, path: str) -> dict:
    """경로 하나에 대한 응답을 만든다. 없는 것은 NotFound, 모양이 어긋난 것은 BadRequest다."""
    if path == "/api/postings":
        return view.postings()
    for pattern, shape, handler in ((POSTING_PATH, POSTING_ID, view.posting), (RESUME_PATH, RESUME_ID, view.resume_match)):
        found = pattern.fullmatch(path)
        if found:
            if not shape.fullmatch(found.group(1)):
                raise BadRequest(path)
            return handler(found.group(1))
    raise NotFound(path)


def make_handler(view: ViewResults, static_root: Path | None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            started = time.monotonic()
            trace_id = trace_id_or_new(self.headers.get("X-Trace-Id"))
            path = self.path.split("?", 1)[0]
            if not path.startswith("/api/"):
                return self._static(path, trace_id)
            try:
                status, body, event, level, error = 200, answer(view, path), "api.requested", "INFO", None
            except NotFound:
                status, body, event, level, error = 404, {"error": "not_found"}, "api.rejected", "WARN", None
            except BadRequest:
                status, body, event, level, error = 400, {"error": "bad_request"}, "api.rejected", "WARN", None
            except Exception as e:
                status, body, event, level, error = 500, {"error": "internal"}, "api.failed", "ERROR", type(e).__name__
            self._send(status, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"), trace_id)
            ms = int((time.monotonic() - started) * 1000)
            log("server", trace_id, event, level, method="GET", path=path, status=status, ms=ms, error=error)

        def _static(self, path: str, trace_id: str) -> None:
            name = "index.html" if path == "/" else path.lstrip("/")
            file = static_root / name if static_root else None
            if file is None or "/" in name or file.suffix not in STATIC_TYPES or not file.is_file():
                return self._send(404, "application/json; charset=utf-8", b'{"error": "not_found"}', trace_id)
            self._send(200, STATIC_TYPES[file.suffix], file.read_bytes(), trace_id)

        def _send(self, status: int, content_type: str, body: bytes, trace_id: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Trace-Id", trace_id)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def serve(view: ViewResults, static_root: Path | None, host: str, port: int) -> None:
    ThreadingHTTPServer((host, port), make_handler(view, static_root)).serve_forever()
