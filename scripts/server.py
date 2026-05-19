#!/usr/bin/env python3
"""
Local dev server for the Clove X dashboard.

Adds two capabilities on top of the static HTML pages:
  - Persona editing (GET/PUT  /api/persona/{slug})
  - Post (re)generation     (POST /api/generate/{slug})
  - Post text fetch         (GET /api/post/{slug}?date=YYYY-MM-DD)

The static HTML pages are served as-is from the repo root. When an HTML
response is sent, a small <script src="/assets/edit.js"> tag is injected
so the UI gains "編集" / "再生成" buttons without touching the generated
files.

Usage:
    python3 scripts/server.py            # http://localhost:8765
    PORT=9000 python3 scripts/server.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS_DIR = REPO_ROOT / "accounts"
OUTPUT_POSTS_DIR = REPO_ROOT / "output" / "posts"
ASSETS_DIR = REPO_ROOT / "assets"

JST = timezone(timedelta(hours=9))

# Lazy import: only needed when generating
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def load_dotenv():
    """Load KEY=VALUE pairs from .env at repo root, without overriding existing env."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and not os.environ.get(key):
            os.environ[key] = value


load_dotenv()


SAFE_SLUG = re.compile(r"^[a-zA-Z0-9_-]+$")


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def is_safe_slug(slug: str) -> bool:
    return bool(SAFE_SLUG.match(slug)) and (ACCOUNTS_DIR / slug).is_dir()


INJECT_SCRIPT = b'<script src="/assets/edit.js" defer></script>\n</body>'


class Handler(BaseHTTPRequestHandler):
    server_version = "CloveDashboard/0.1"

    # ---------------- helpers ----------------
    def _send_json(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str, content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ---------------- routing ----------------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            return self._handle_api_get(path, urllib.parse.parse_qs(parsed.query))

        if path == "/assets/edit.js":
            return self._serve_static(ASSETS_DIR / "edit.js", "application/javascript; charset=utf-8")

        return self._serve_static_html_or_file(path)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/persona/"):
            slug = parsed.path[len("/api/persona/"):]
            return self._put_persona(slug)
        return self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/generate/"):
            slug = parsed.path[len("/api/generate/"):]
            return self._post_generate(slug, urllib.parse.parse_qs(parsed.query))
        return self._send_json(404, {"error": "not found"})

    # ---------------- static ----------------
    def _serve_static_html_or_file(self, path: str):
        if path == "/" or path == "":
            path = "/index.html"

        rel = path.lstrip("/")
        # prevent path traversal
        target = (REPO_ROOT / rel).resolve()
        if REPO_ROOT.resolve() not in target.parents and target != REPO_ROOT.resolve():
            return self._send_text(403, "forbidden")
        if not target.exists() or not target.is_file():
            return self._send_text(404, "not found")

        if target.suffix == ".html":
            html = target.read_bytes()
            # inject our edit.js right before </body>
            if b"</body>" in html and b"/assets/edit.js" not in html:
                html = html.replace(b"</body>", INJECT_SCRIPT, 1)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html)
            return

        ctype = {
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".md": "text/plain; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".ico": "image/x-icon",
        }.get(target.suffix, "application/octet-stream")
        return self._serve_static(target, ctype)

    def _serve_static(self, path: Path, content_type: str):
        if not path.exists():
            return self._send_text(404, "not found")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------------- API: GET ----------------
    def _handle_api_get(self, path: str, query: dict):
        if path == "/api/accounts":
            slugs = sorted([
                d.name for d in ACCOUNTS_DIR.iterdir()
                if d.is_dir() and (d / "persona.md").exists()
            ])
            return self._send_json(200, {"slugs": slugs})

        if path.startswith("/api/persona/"):
            slug = path[len("/api/persona/"):]
            return self._get_persona(slug)

        if path.startswith("/api/post/"):
            slug = path[len("/api/post/"):]
            date = (query.get("date") or [today_jst()])[0]
            return self._get_post(slug, date)

        return self._send_json(404, {"error": "not found"})

    def _get_persona(self, slug: str):
        if not is_safe_slug(slug):
            return self._send_json(400, {"error": "invalid slug"})
        p = ACCOUNTS_DIR / slug / "persona.md"
        if not p.exists():
            return self._send_json(404, {"error": "persona missing"})
        return self._send_json(200, {"slug": slug, "content": p.read_text(encoding="utf-8")})

    def _put_persona(self, slug: str):
        if not is_safe_slug(slug):
            return self._send_json(400, {"error": "invalid slug"})
        data = self._read_json()
        if data is None or "content" not in data:
            return self._send_json(400, {"error": "missing content"})
        content = data["content"]
        if not isinstance(content, str):
            return self._send_json(400, {"error": "content must be string"})
        if len(content) > 50000:
            return self._send_json(400, {"error": "content too large"})
        p = ACCOUNTS_DIR / slug / "persona.md"
        p.write_text(content, encoding="utf-8")
        return self._send_json(200, {"slug": slug, "saved": True, "bytes": len(content.encode("utf-8"))})

    def _get_post(self, slug: str, date: str):
        if not is_safe_slug(slug):
            return self._send_json(400, {"error": "invalid slug"})
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            return self._send_json(400, {"error": "invalid date"})
        p = ACCOUNTS_DIR / slug / "posts" / f"{date}.md"
        if not p.exists():
            return self._send_json(404, {"error": "no post"})
        return self._send_json(200, {"slug": slug, "date": date, "text": p.read_text(encoding="utf-8")})

    # ---------------- API: generate ----------------
    def _post_generate(self, slug: str, query: dict):
        if not is_safe_slug(slug):
            return self._send_json(400, {"error": "invalid slug"})
        date = (query.get("date") or [today_jst()])[0]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            return self._send_json(400, {"error": "invalid date"})

        try:
            import anthropic  # noqa: F401
            from generate_daily_posts import generate_post_for_account
        except Exception as e:
            return self._send_json(500, {"error": f"import failed: {e}"})

        if not os.environ.get("ANTHROPIC_API_KEY"):
            return self._send_json(500, {"error": "ANTHROPIC_API_KEY not set in server environment"})

        import anthropic
        client = anthropic.Anthropic()

        now_jst = datetime.fromisoformat(f"{date}T{datetime.now(JST).strftime('%H:%M:%S')}+09:00")
        try:
            text, err = generate_post_for_account(client, slug, now_jst)
        except Exception as e:
            return self._send_json(500, {"error": f"generate failed: {e}"})

        if err or not text:
            return self._send_json(500, {"error": err or "empty result"})

        post_path = ACCOUNTS_DIR / slug / "posts" / f"{date}.md"
        post_path.parent.mkdir(parents=True, exist_ok=True)
        post_path.write_text(text, encoding="utf-8")

        # also update the summary JSON in output/posts/{date}.json so the rendered
        # dashboards stay in sync if they are regenerated later.
        summary_path = OUTPUT_POSTS_DIR / f"{date}.json"
        summary = []
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                summary = []
        replaced = False
        for entry in summary:
            if isinstance(entry, dict) and entry.get("slug") == slug:
                entry["text"] = text
                entry["status"] = "regenerated"
                entry["date"] = date
                replaced = True
                break
        if not replaced:
            summary.append({"slug": slug, "date": date, "text": text, "status": "regenerated"})
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        return self._send_json(200, {"slug": slug, "date": date, "text": text})


def main():
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Clove dashboard server on http://localhost:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
