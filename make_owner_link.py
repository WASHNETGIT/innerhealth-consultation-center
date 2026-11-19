"""Print the one link to send the clinic owner.

The owner only has a phone, so she never copies a code. She opens this link, taps Allow,
and Google returns her to the dashboard, which saves the token by itself.

Usage:
    export GOOGLE_CLIENT_ID=...
    export GOOGLE_CLIENT_SECRET=...
    python3 make_owner_link.py
"""
from __future__ import annotations

import argparse
import os
import sys

CLINIC_EMAIL = os.getenv("CLINIC_EMAIL", "innerhealthconsult@gmail.com")


def main() -> int:
    ap = argparse.ArgumentParser(description="Owner connect link for Inner Health email.")
    ap.add_argument("--base", default=os.getenv("PUBLIC_BASE_URL",
                    "https://innerhealth-consultation-center.onrender.com"),
                    help="the public site URL")
    ap.add_argument("--check", action="store_true", help="verify the server has the credentials")
    args = ap.parse_args()

    if args.check:
        missing = [n for n in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET") if not os.getenv(n, "").strip()]
        if missing:
            print("Missing on this machine: " + ", ".join(missing), file=sys.stderr)
            return 2
        print("Both values are set here. The server needs the same two in Render's environment.")
        return 0

    link = args.base.rstrip("/") + "/api/google/start"
    print(link)
    print()
    print("Send that to the owner. She taps it, signs in as " + CLINIC_EMAIL +
          ", taps Allow, and she is done.")
    print("No code to copy. The server stores the token and starts sending.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
