#!/usr/bin/env python3
"""One-shot Google OAuth bootstrap with local browser popup.

This mirrors the n8n-style UX: open browser, sign in, capture callback, persist token.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        print(f"Missing required env var: {name}")
        sys.exit(1)
    return value


def main() -> int:
    load_dotenv()

    client_id = _require("GOOGLE_CALENDAR_CLIENT_ID")
    client_secret = _require("GOOGLE_CALENDAR_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_CALENDAR_REDIRECT_URI", "http://localhost:8080/oauth2callback").strip()
    token_path = Path(os.getenv("GOOGLE_CALENDAR_TOKEN_PATH", "~/.yak/google_calendar_token.json")).expanduser()

    scopes_env = os.getenv(
        "GOOGLE_CALENDAR_SCOPES",
        "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events",
    )
    scopes = [s for s in scopes_env.split() if s]

    redirect = urlparse(redirect_uri)
    if redirect.scheme not in {"http", "https"}:
        print("GOOGLE_CALENDAR_REDIRECT_URI must be http(s) URI")
        return 1
    if not redirect.hostname or not redirect.port:
        print("GOOGLE_CALENDAR_REDIRECT_URI must include host and port")
        return 1

    client_config = {
        "web": {
            "client_id": client_id,
            "project_id": os.getenv("GOOGLE_CALENDAR_PROJECT_ID", "yak-local"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=scopes)
    flow.redirect_uri = redirect_uri

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    code_holder: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if parsed.path != (redirect.path or "/"):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            if qs.get("state", [""])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch")
                return

            code = qs.get("code", [""])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing code")
                return

            code_holder["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Google auth complete.</h2><p>You can close this window.</p></body></html>"
            )

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer((redirect.hostname, redirect.port), CallbackHandler)
    print(f"Opening browser for Google sign-in: {auth_url}")
    webbrowser.open(auth_url)
    print("Waiting for OAuth callback...")

    while "code" not in code_holder:
        server.handle_request()

    flow.fetch_token(code=code_holder["code"])
    creds = flow.credentials

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    print(f"Saved token to {token_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
