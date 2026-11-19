# Inner Health Consultation Center — project file

Where it lives: `/home/washnet/business-dashboard`
Repo: https://github.com/WASHNETGIT/innerhealth-consultation-center (private, branch `main`)
Last commit here: `91dee73`

## What it is
Booking and admin system for a wellness scan clinic in Sunnyside, Pretoria.
Guests book a scan at `/book`; the clinic runs the day from the admin dashboard at `/`.

## Where it runs
- Local service: `http://127.0.0.1:8010` — systemd unit `inner-health`
  (`/etc/systemd/system/inner-health.service`), started by `uvicorn main:app`.
  Takes about 35 seconds to come up after a restart: wait, do not assume it crashed.
- Live: https://innerhealth-consultation-center.onrender.com (Render free plan, sleeps when idle)
- Local settings: `.env` (never committed)

## The agent
- Complex questions run on the **M2 Max** over ZeroTier (`10.147.19.136:11434`, `qwen3:4b`).
- Fallback: this machine's Ollama (`127.0.0.1:11434`, `llama3.2:latest`).
- Health check: `GET /api/assistant/health` shows both backends.
- Admin answers are computed from the database and shown as written. A model may only
  reword them, and only if the rewrite keeps every figure identical.
- Product questions are answered from `static/products/catalog.json` (78 products), and
  a product code is an exact identifier. Short follow-ups inherit the previous topic.

## Money and bookings
- Services: full-body scan R450 (R150 non-refundable deposit), follow-up scan R450.
- Deposits are EFT: FNB, Ntombikayise N Mkhaliphi, account 62804835835, branch 250655, cheque.
- After booking, a guest can submit proof of payment (JPG/PNG/WebP/PDF, 8MB max) at
  `POST /api/public/bookings/{reference}/proof`; files land in `uploads/proofs/`.

## Gotchas learned the hard way
- `create_all()` never alters an existing table. New columns need a manual `ALTER TABLE`
  on `business_hub.db`, or every bookings query fails and the calendar returns 500.
- The booking model is `PublicBooking`, not `Booking`.
- Use `127.0.0.1`, not `localhost`.
- Backups are saved as `*.bak-<timestamp>` beside each edited file; they are gitignored.

## Open items
- No card gateway configured (`DEPOSIT_CHECKOUT_URL` is empty), so the pay button stays
  hidden and guests pay by EFT.
- Render cannot reach the M2 Max, so production runs in rules mode.
- Admin password is still a stub (`require_admin()` returns True) — deferred by decision.
- Gmail sending needs `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` set on Render.
