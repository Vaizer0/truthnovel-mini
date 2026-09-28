#!/usr/bin/env python3
"""Local dev relay: serves this repo over HTTP and proxies page fetches.

Why this exists
---------------
GitHub Pages is static, so it cannot proxy requests. Locally we can: this
server serves index.html and exposes /_p?url=... which relays the upstream
fetch. The page uses that route automatically when it is loaded from
localhost (see the `chain()` function in index.html).

    python3 tools/local-relay.py 8080
    # then open http://127.0.0.1:8080/index.html

Only needed for local/offline development. The hosted page uses the Cloudflare
Worker in worker/ instead.
"""
import hashlib
import os
import subprocess
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".relay-cache")
JINA = "https://r.jina.ai/"
TTL = 60 * 60 * 24 * 30
os.makedirs(CACHE, exist_ok=True)


def jina_fetch(url, timeout=90):
    # NOTE: deliberately no custom User-Agent. r.jina.ai returns 403 to browser
    # User-Agents, so curl's default UA is the only one it accepts.
    p = subprocess.run(
        [
            "curl", "-sS", "--compressed", "-m", str(timeout),
            "-H", "X-Return-Format: html",
            "-w", "\n__CODE__%{http_code}",
            JINA + url,
        ],
        capture_output=True,
    )
    raw = p.stdout.decode("utf-8", "replace")
    if "__CODE__" not in raw:
        raise ValueError("curl failed: %s" % p.stderr.decode("utf-8", "replace")[:200])
    body, _, code = raw.rpartition("\n__CODE__")
    if code.strip() != "200":
        raise ValueError("upstream HTTP %s" % code.strip())
    if len(body) < 2000:
        raise ValueError("upstream returned %d bytes" % len(body))
    return body


def cached(url):
    path = os.path.join(CACHE, hashlib.sha256(url.encode()).hexdigest() + ".html")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < TTL:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    last = None
    for attempt in range(3):
        try:
            body = jina_fetch(url)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            return body
        except Exception as e:
            last = e
            time.sleep(2 + attempt * 3)
    raise last


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_body(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/_p":
            url = (urllib.parse.parse_qs(parsed.query).get("url") or [""])[0]
            if not url.startswith(("http://", "https://")):
                return self.send_body(400, "bad url", "text/plain")
            try:
                return self.send_body(200, cached(url))
            except Exception as e:
                return self.send_body(502, "upstream failed: %s" % e, "text/plain")
        rel = parsed.path.lstrip("/") or "index.html"
        target = os.path.normpath(os.path.join(ROOT, rel))
        if not target.startswith(ROOT) or not os.path.isfile(target):
            return self.send_body(404, "not found", "text/plain")
        ctype = "text/plain" if target.endswith((".py", ".md", ".toml", ".js", ".yml")) else "text/html; charset=utf-8"
        with open(target, encoding="utf-8", errors="replace") as f:
            return self.send_body(200, f.read(), ctype)

    def log_message(self, fmt, *a):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % a))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print("serving %s on http://127.0.0.1:%d/index.html" % (ROOT, port))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
