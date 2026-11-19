"""Inner Health Consultation Center - standalone mailer.

Sends booking confirmations and reminders from the clinic's own Gmail using a
Google OAuth refresh token. Designed to be dropped onto any machine or server
that has Python 3.9+ and nothing else installed - it uses only the standard library.

Usage
-----
    export GOOGLE_CLIENT_ID=...
    export GOOGLE_CLIENT_SECRET=...
    export GOOGLE_REFRESH_TOKEN=1//...
    python3 smtp_mailer.py --to client@example.com --subject "Your scan" --body "..."

Or from Python:
    from smtp_mailer import send_email
    result = send_email("client@example.com", "Your scan", "Hello ...")
    # -> {"sent": True, "via": "gmail", "id": "..."}

Exit codes: 0 sent, 1 failed, 2 not configured.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Any, Dict, Optional

CLINIC_EMAIL = os.getenv("CLINIC_EMAIL", "innerhealthconsult@gmail.com")
CLINIC_NAME = "Inner Health Consultation Center"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _explain(detail: str) -> None:
    """Turn Google's error code into the actual thing to fix."""
    hints = {
        "invalid_client": "The Client ID or Client secret is wrong, or belongs to a different project. "
                          "Re-copy both from Google Cloud > APIs & Services > Credentials.",
        "invalid_grant": "The refresh token has been revoked, has expired, or was issued for a different "
                         "Client ID. Remove access at myaccount.google.com/permissions and repeat the "
                         "playground step to get a new one.",
        "unauthorized_client": "The OAuth client is not a Web application type. Recreate it as Web application.",
        "invalid_scope": "The gmail.send scope was not granted. Repeat the playground step and make sure "
                         "the scope box contains https://www.googleapis.com/auth/gmail.send.",
    }
    for code, hint in hints.items():
        if code in detail:
            print(f"FIX: {hint}", file=sys.stderr)
            return
    print("FIX: check the three values were copied in full, with no spaces or line breaks.",
          file=sys.stderr)


def get_access_token(timeout: int = 20) -> Optional[str]:
    """Exchange the refresh token for a short-lived access token (about 1 hour)."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    missing = [n for n, v in (
        ("GOOGLE_CLIENT_ID", client_id),
        ("GOOGLE_CLIENT_SECRET", client_secret),
        ("GOOGLE_REFRESH_TOKEN", refresh_token),
    ) if not v]
    if missing:
        print(f"Not configured, missing: {', '.join(missing)}", file=sys.stderr)
        return None

    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(
        TOKEN_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
        token = payload.get("access_token")
        if not token:
            print(f"No access_token in response: {payload}", file=sys.stderr)
        return token
    except urllib.error.HTTPError as exc:
        # The body says exactly what is wrong, e.g. invalid_grant for a revoked token
        detail = exc.read().decode("utf-8", "ignore")
        print(f"Token exchange failed ({exc.code}): {detail}", file=sys.stderr)
        _explain(detail)
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"Token exchange failed: {exc}", file=sys.stderr)
        return None


def build_message(to_addr: str, subject: str, body: str,
                  html: bool = False,
                  reply_to: Optional[str] = None,
                  from_name: str = CLINIC_NAME,
                  from_email: str = CLINIC_EMAIL) -> EmailMessage:
    """Build a proper MIME message with a friendly From name."""
    if not to_addr or "@" not in to_addr:
        raise ValueError(f"Not a valid email address: {to_addr!r}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_addr
    if reply_to:
        msg["Reply-To"] = reply_to

    if html:
        msg.set_content("This message is best viewed in an HTML capable email reader.")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)
    return msg


def send_email(to_addr: str, subject: str, body: str,
               html: bool = False,
               reply_to: Optional[str] = None,
               timeout: int = 30) -> Dict[str, Any]:
    """Send one email as the clinic. Returns a dict describing what happened."""
    try:
        msg = build_message(to_addr, subject, body, html=html, reply_to=reply_to)
    except ValueError as exc:
        return {"sent": False, "via": None, "reason": str(exc)}

    token = get_access_token(timeout=timeout)
    if not token:
        return {"sent": False, "via": None, "reason": "could not get an access token"}

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    req = urllib.request.Request(
        SEND_URL,
        data=json.dumps({"raw": raw}).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read() or b"{}")
        return {"sent": True, "via": "gmail", "id": payload.get("id"),
                "thread": payload.get("threadId")}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        return {"sent": False, "via": "gmail", "reason": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"sent": False, "via": "gmail", "reason": str(exc)}


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Send an email as Inner Health Consultation Center.")
    parser.add_argument("--to", help="recipient address")
    parser.add_argument("--subject")
    parser.add_argument("--body", help="message text")
    parser.add_argument("--body-file", help="read the message from this file instead")
    parser.add_argument("--html", action="store_true", help="treat the body as HTML")
    parser.add_argument("--check", action="store_true", help="only verify the credentials work")
    args = parser.parse_args()

    if args.check:
        token = get_access_token()
        if token:
            print("Credentials OK - an access token was issued.")
            return 0
        print("Credentials FAILED. See the message above.")
        return 2

    if not args.to or not args.subject:
        parser.error("--to and --subject are required unless you pass --check")

    body = args.body
    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as fh:
            body = fh.read()
    if not body:
        parser.error("give --body or --body-file")

    result = send_email(args.to, args.subject, body, html=args.html)
    print(json.dumps(result, indent=2))
    return 0 if result.get("sent") else 1


if __name__ == "__main__":
    sys.exit(_cli())
