#!/usr/bin/env python3
"""Sajikan frontend RAPIIN (hasil build) + teruskan /api ke backend.

Pilot/testing saja: untuk produksi gunakan image Docker yang menyajikan
frontend + API dari satu origin. Stdlib only, tanpa dependensi baru.

Contoh:
    python3 ops/serve_dashboard.py --dist /path/ke/hafgufa/dist --port 5175
    tailscale serve --https=8443 --bg http://localhost:5175
"""
from __future__ import annotations

import argparse
import mimetypes
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOP = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailer', 'transfer-encoding', 'upgrade', 'content-length', 'host',
}


def make_handler(dist: Path, backend: str):
    dist = dist.resolve()

    def inside(path: Path) -> bool:
        try:
            path.relative_to(dist)
            return True
        except ValueError:
            return False

    class Handler(BaseHTTPRequestHandler):
        server_version = 'RapiinDashboard/1'

        def log_message(self, *args):
            pass

        def _serve_file(self, path: Path):
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',
                             mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _static(self):
            rel = self.path.split('?', 1)[0].lstrip('/')
            target = (dist / rel).resolve() if rel else dist / 'index.html'
            if rel and inside(target) and target.is_file():
                self._serve_file(target)
            else:
                # SPA fallback untuk /login, /settings, /supervisor, ...
                self._serve_file(dist / 'index.html')

        def _proxy(self):
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            req = urllib.request.Request(backend + self.path, data=body,
                                         headers=headers, method=self.command)
            try:
                upstream = urllib.request.urlopen(req, timeout=120)
            except urllib.error.HTTPError as exc:
                upstream = exc
            self.send_response(upstream.status)
            ctype = upstream.headers.get('Content-Type', '')
            for key, value in upstream.headers.items():
                if key.lower() in HOP:
                    continue
                if 'text/event-stream' in ctype and key.lower() == 'content-length':
                    continue
                self.send_header(key, value)
            self.end_headers()
            while True:
                chunk = upstream.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

        def _route(self):
            if self.path == '/ready' or self.path.startswith('/api/'):
                self._proxy()
            elif self.command == 'GET':
                self._static()
            else:
                self.send_error(404)

        do_GET = _route
        do_POST = _route
        do_PUT = _route
        do_PATCH = _route
        do_DELETE = _route

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description='Sajikan dashboard RAPIIN + proxy /api.')
    parser.add_argument('--dist', required=True, help='folder hasil build frontend (dist/)')
    parser.add_argument('--backend', default='http://127.0.0.1:8000')
    parser.add_argument('--port', type=int, default=5175)
    args = parser.parse_args()
    handler = make_handler(Path(args.dist), args.backend)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler).serve_forever()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
