"""Build the one link the clinic owner taps to authorise email sending.

She opens the link, signs in with the clinic Google account, clicks Allow, and Google
shows her a code on the page. She sends that code back. It is exchanged for a refresh
token server-side, so the client secret never leaves this machine.

Usage:
    export GOOGLE_CLIENT_ID=...
    export GOOGLE_CLIENT_SECRET=...
    python3 make_owner_link.py                # prints the link
    python3 make_owner_link.py --exchange CODE  # turns her code into a refresh token
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REDIRECT = "urn:ietf:wg:oauth:2.0:oob"          # out-of-band: Google shows the code on screen
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/gmail.send"
CLINIC_EMAIL = os.getenv("CLINIC_EMAIL", "innerhealthconsult@gmail.com")


def build_link(client_id: str, login_hint: str = CLINIC_EMAIL) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",     # this is what produces a refresh token
        "prompt": "consent",          # forces the refresh token even if she allowed before
        "login_hint": login_hint,     # pre-fills the right account
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange(code: str, client_id: str, client_secret: str) -> dict:
    data = urllib.parse.urlencode({
        "code": code.strip(),
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return {"error": exc.code, "detail": exc.read().decode("utf-8", "ignore")}


def main() -> int:
    ap = argparse.ArgumentParser(description="Owner authorisation link for Inner Health email.")
    ap.add_argument("--exchange", metavar="CODE", help="her authorisation code, to swap for a refresh token")
    ap.add_argument("--hint", default=CLINIC_EMAIL, help="which Google account to pre-fill")
    args = ap.parse_args()

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

    if args.exchange:
        if not client_id or not client_secret:
            print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first.", file=sys.stderr)
            return 2
        result = exchange(args.exchange, client_id, client_secret)
        if result.get("refresh_token"):
            print("SUCCESS\n")
            print("GOOGLE_CLIENT_ID=" + client_id)
            print("GOOGLE_CLIENT_SECRET=" + client_secret)
            print("GOOGLE_REFRESH_TOKEN=" + result["refresh_token"])
            return 0
        print("No refresh token returned:", file=sys.stderr)
        print(json.dumps(result, indent=2), file=sys.stderr)
        if "invalid_grant" in json.dumps(result):
            print("FIX: the code was already used or has expired (they last about 10 minutes). "
                  "Ask her to open the link again and send a fresh one.", file=sys.stderr)
        return 1

    if not client_id:
        print("Set GOOGLE_CLIENT_ID first, or paste the link template below with your own value.",
              file=sys.stderr)
        client_id = "YOUR_CLIENT_ID"
    print(build_link(client_id, args.hint))
    return 0


if __name__ == "__main__":
    sys.exit(main())
