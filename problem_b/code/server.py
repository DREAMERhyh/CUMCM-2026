"""Local visualization server; Python standard library only. No official API."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from environment import calculate, demo, generate

WEB = Path(__file__).resolve().parent / "visualization"
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css")}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="application/json"):
        payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode() if content_type == "application/json" else body
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/demo":
            return self.send(200, calculate(demo()))
        if path in STATIC:
            name, kind = STATIC[path]
            return self.send(200, (WEB/name).read_bytes(), kind)
        self.send(404, {"error": "页面不存在。"})

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 200_000:
                raise ValueError("输入为空或超过 200 KB。")
            data = json.loads(self.rfile.read(size))
            path = urlsplit(self.path).path
            if path == "/api/calculate":
                result = calculate(data)
            elif path == "/api/generate":
                result = calculate(generate(data))
            else:
                return self.send(404, {"error": "接口不存在。"})
            self.send(200, result)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            self.send(400, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description="B题前两问 · 本地几何实验窗口")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"B题几何实验窗口：http://127.0.0.1:{server.server_port}", flush=True)
        print("请在浏览器打开以上地址。按 Ctrl+C 结束。", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
