# Inner Health Consultation Center — Scan Booking & Command Center

A cloud-first full-body scan booking and client management system built with **FastAPI**, **SQLAlchemy**, PostgreSQL in cloud, and SQLite for a local fallback. The existing multi-venture tools remain available in the same app.

## Features

- **Scan booking** – Public appointments, R150 deposit state, R300 balance collection, scan report queue and client management
- **Scan command center** – Live LED states, revenue analytics, peak periods, client retention and walk-in sales
- **5 Pillars** – InnerHealth, Sound Engineering, IT Services, Driving School, Beauty & Nails legacy tools
- **Unified Scheduling** – Weekly thematic calendar with auto-conflict detection
- **Centralized CRM** – Client management, appointments, service records, contact logs
- **Inventory Tracking** – Stock levels with low-stock alerts
- **Natural Language Commands** – Quick actions like *"Book John for a driving lesson on Thursday at 10 AM"* or *"Add 5 units of protein supplement to InnerHealth stock"*
- **Automated Reminders** – Placeholder hook system for SMS/WhatsApp/Email notifications
- **Live Dashboard** – Real-time stats: total clients, upcoming appointments, low-stock items, pending reminders

## Project Structure

```
business-dashboard/
├── main.py              # FastAPI app, SQLAlchemy models, API endpoints
├── static/
│   └── index.html       # Full-featured SPA dashboard (Tailwind + Alpine.js)
└── requirements.txt     # Python dependencies
```

## Setup

1. **Install dependencies**
   ```bash
   cd business-dashboard
   pip install -r requirements.txt
   ```

2. **Run the server**
   ```bash
   uvicorn main:app --reload
   ```
   The API will be available at `http://localhost:8000`

3. **Access the dashboard**
   Open your browser to `http://localhost:8000`

## Quick Start

- **Refresh** the page to see the overview
- **Click "New Appointment"** to schedule a lesson, client meeting, or service
- **Click "Add Client"** to register a new business client
- **Click "Add Item"** to track inventory (InnerHealth supplements, IT parts, etc.)
- **Use the command bar** (bottom) to issue natural-language commands:
  - *"Book John for a driving lesson on Thursday at 10 AM"*
  - *"Add 5 units of protein supplement to InnerHealth stock"*
  - *"Register client Mary for beauty services"*

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Home dashboard |
| GET | `/api/pillars` | Pillar metadata |
| GET | `/api/clients` | Client list (with pillar filter) |
| POST | `/api/clients` | Create a new client |
| GET | `/api/clients/{id}` | Get client details + appointments + services |
| PUT | `/api/clients/{id}` | Update client |
| DELETE | `/api/clients/{id}` | Delete client |
| GET | `/api/appointments` | List appointments (with week_start filter) |
| POST | `/api/appointments` | Create an appointment |
| PUT | `/api/appointments/{id}` | Update appointment |
| DELETE | `/api/appointments/{id}` | Delete appointment |
| GET | `/api/inventory` | Inventory list (low_stock filter) |
| POST | `/api/inventory` | Add inventory item |
| PUT | `/api/inventory/{id}/adjust` | Adjust stock quantity |
| GET | `/api/reminders` | List pending reminders |
| POST | `/api/reminders/generate` | Auto-generate reminders |
| POST | `/api/reminders/send-all` | Send all pending reminders |
| POST | `/api/command` | Process natural-language command |
| GET | `/api/health` | Health check |

## Architecture

- **Backend**: FastAPI + SQLAlchemy ORM (PostgreSQL in cloud, SQLite fallback)
- **Frontend**: Single-page app with Tailwind CSS + Alpine.js
- **Data Store**: PostgreSQL for cloud-first deployment; SQLite when `DATABASE_URL` is unset
- **State Management**: React-like reactive state via Alpine.js

## Extending

- **Add new pillars** – Edit `PILLARS` list in `main.py`
- **Custom reminders** – Replace the placeholder `sendReminder()` function with real SMS/WhatsApp API calls
- **More command types** – Extend the `runCommand()` handler in `main.py`
- **Advanced scheduling** – Integrate with Google Calendar or Outlook via Alpine.js JS

## License

MIT

## Inner Health Consultation Center booking system

The dashboard now includes a public booking flow and a separate appointment control center:

- Public booking: `http://localhost:8000/book`
- Admin booking control center: `http://localhost:8000/admin/bookings`
- Existing multi-venture dashboard: `http://localhost:8000/`

On startup, SQLAlchemy creates the booking tables and seeds three consultation services. Default hours are Monday–Friday 09:00–17:00, Saturday 09:00–15:00, and Sunday closed. The full-body scan consultation is R450 with a R150 deposit. The booking flow displays the non-refundable deposit. Pending bookings show EFT instructions from `.env`; an admin verifies the transfer and marks the deposit received before confirming the booking. The booking schema is documented in `migrations/001_booking_system.sql`.

### Configuration

Copy `.env.example` to `.env`, then change `ADMIN_PASSWORD` and set `BOOKING_TOKEN_SECRET` to a separate long random value before exposing this service. `PUBLIC_BASE_URL` must be the public HTTPS origin so that emailed management links work outside localhost. The admin API uses HTTP Basic credentials; terminate HTTPS at a trusted reverse proxy before using it beyond a private development network. Admins can also change the password from the **Change password** button in the scan dashboard; that password is stored as a salted hash in the configured database and takes effect immediately. Back up the database so the changed credential remains available after recovery or migration.

Optional email notifications use Resend over HTTPS (`RESEND_API_KEY`, `RESEND_FROM`) or SMTP locally; WhatsApp uses `WHATSAPP_WEBHOOK_URL`. The webhook receives JSON with `to` and `message` fields; connect it to a WhatsApp Business API or Twilio adapter you operate. Notification failures are logged and do not undo a booking.

The dashboard assistant tries the M4 Ollama first and local Ollama second. Set `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_FALLBACK_BASE_URL`, and `OLLAMA_FALLBACK_MODEL`. The health endpoint reports both connections. To create the local fallback model on this host, run `bash setup-local-ollama-fallback.sh`; it starts loopback Ollama and pulls `llama3.2:3b`. The M4 scan worker uses an outbound HTTPS queue poll and calls Ollama locally on the M4; the cloud host does not need private network access into ZeroTier.

### Local setup

```sh
cd business-dashboard
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set a strong ADMIN_PASSWORD, BOOKING_TOKEN_SECRET, and correct PUBLIC_BASE_URL
uvicorn main:app --host 0.0.0.0 --port 8000
```

Keep `.env` and `business_hub.db` private and back up the database regularly. The public booking page is unauthenticated. Admin APIs require the configured credentials. Booking management links contain a signed per-booking token; only its hash is stored in SQLite.

### Hourly reminders

The reminder endpoint sends 24-hour and 2-hour reminders and marks a reminder sent only after at least one configured channel accepts it. Add this cron entry (adjust the absolute path):

```cron
0 * * * * /home/washnet/business-dashboard/run-booking-reminders.sh >> /home/washnet/business-dashboard/reminders.log 2>&1
```

Email and WhatsApp require their optional provider configuration. Without a delivery channel, reminders stay pending for a later retry.

### Booking endpoints

Public endpoints: `GET /api/public/services`, `GET /api/public/calendar?month=YYYY-MM&service_id=ID`, `GET /api/public/slots?day=YYYY-MM-DD&service_id=ID`, and `POST /api/public/bookings`. Token based management supports booking details, rescheduling, cancellation, and `.ics` downloads under `/api/public/manage/{token}`. Admin APIs under `/api/admin` require Basic authentication and manage bookings, services, weekly working hours, and blocked dates.


### Cloud first with local fallback

Deploy the Docker image to your preferred cloud container host and attach a managed PostgreSQL database. Set `DATABASE_URL` to its PostgreSQL connection URL, along with strong `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `BOOKING_TOKEN_SECRET`, `PUBLIC_BASE_URL`, and notification credentials. The app creates missing tables on startup; back up the managed database and use a persistent database service rather than container-local storage. The included `Dockerfile` supports common container platforms. `docker-compose.yml` is for a Postgres-backed deployment or local staging.

Use the cloud URL as the normal booking and dashboard address. Keep this app running on a trusted local host as a fallback at its local/ZeroTier URL, with `DATABASE_URL` pointed at the same reachable PostgreSQL database when available. If the cloud database itself is unreachable, the local server can use SQLite by leaving `DATABASE_URL` unset; those offline writes are a separate copy and must be reconciled after recovery. This is an application-server fallback, not automatic database failover or write synchronization.

The Ollama brain stays on the M4. The M4 worker at `m4_scan_agent.py` polls the cloud queue outbound over HTTPS and calls the M4 Ollama locally; the cloud does not connect into ZeroTier. Set the same random `AI_AGENT_KEY` in the cloud environment and the M4 environment. On the M4, set `CLOUD_API_URL` to the deployed app URL, `M4_OLLAMA_URL` to the Ollama listener, and `AI_MODEL` to a model installed on that Mac (`ollama list`). Do not expose the Ollama port to the public internet. Only bookings with scan input are picked up by the worker.

Set a cloud scheduler to call `POST https://YOUR-CLOUD-HOST/api/admin/reminders/run` hourly using HTTP Basic authentication. The included shell cron script is intended for a local server with a `.env` file.


### Scan queue worker on the M4

Copy `m4_scan_agent.py` to the Mac mini. After setting the M4 Ollama endpoint and verifying `ollama list`, run the worker with environment values configured in your shell or launch agent:

```sh
export CLOUD_API_URL=https://YOUR-APP.onrender.com
export AI_AGENT_KEY='the-same-long-random-secret-set-in-cloud'
export M4_OLLAMA_URL=http://10.147.19.146:11434
export AI_MODEL=llama3.2:3b
python3 m4_scan_agent.py
```

The worker only picks up bookings with scan data entered by an operator and a paid deposit. It sends the measurements to the local Ollama model, then saves a report for practitioner review in the cloud booking record. Do not put real scan data into the demo seed. Use HTTPS for the cloud URL and keep the agent key secret.

### Demo scan data

After configuring a development database, run `python3 seed_scan_demo.py` once. It creates ten clearly fake clients, a rolling year of booking/revenue history, example floor states, and two same-day sales. It refuses to run if bookings already exist. Do not run this against production data.

### Free public hosting

`render.yaml` prepares a free Render web service. It needs a PostgreSQL URL from Supabase or another provider and the secrets listed in `.env.example`. Render supplies a public HTTPS `onrender.com` address; copy it into `PUBLIC_BASE_URL` after deployment. Free services can sleep while idle, so the first request can be delayed, and free database tiers may pause or expire. This is suitable for a demo; verify current provider limits and back up data before relying on it for live client bookings.

### Social links

Set `WHATSAPP_NUMBER=2785771853` for the public booking page contact button. Facebook, Instagram, and TikTok profile links are optional environment variables; leave them blank until those profiles are ready. WhatsApp booking notifications use the separate `WHATSAPP_WEBHOOK_URL` delivery integration.

### EFT deposit handling

Bookings start as `pending_deposit` and display the configured bank account, R150 amount, and unique `SCN-####` reference. Enter the account details in `.env`. After checking the transfer in the bank account, use **Confirm R150 deposit** in the admin schedule; this changes the booking to confirmed and releases check-in actions. The system does not automatically verify EFT transfers. A hosted payment provider can be added later through `DEPOSIT_CHECKOUT_URL` and `/api/payments/deposit/confirm` with a `PAYMENT_WEBHOOK_SECRET`.
