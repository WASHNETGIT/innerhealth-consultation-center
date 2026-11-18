# Inner Health Consultation Center — Engineering Handover & Context

**Generated**: 2026-11-18  
**Repository**: [WASHNETGIT/innerhealth-consultation-center](https://github.com/WASHNETGIT/innerhealth-consultation-center)  
**Live Production URL**: [https://innerhealth-consultation-center.onrender.com](https://innerhealth-consultation-center.onrender.com)  

---

## 1. Project Locations & Environment

- **Root Directory**: `/home/washnet/business-dashboard`
- **Virtual Environment**: `/home/washnet/business-dashboard/.venv`
- **Main App File**: `/home/washnet/business-dashboard/main.py` (FastAPI backend + Jinja2/Static mounts)
- **Static Assets & HTML**: `/home/washnet/business-dashboard/static/`
  - `book.html`: Public patient booking portal (`/book`)
  - `manage.html`: Patient appointment view/cancel/reschedule portal (`/manage/{token}`)
  - `index.html`: Admin Business Hub & Client Directory (`/`)
  - `scan-dashboard.html`: Live Scan Command Center & Quantum evaluation workspace (`/admin/bookings` or `/scan`)
- **Database**: SQLite at `/home/washnet/business-dashboard/business_hub.db`
- **Environment Config**: `/home/washnet/business-dashboard/.env`
- **Render Deployment Blueprint**: `/home/washnet/business-dashboard/render.yaml`
- **Systemd Service**: `inner-health.service` running on local port `8000`

---

## 2. Business Setup & Constraints

- **Business Name**: **Inner Health Consultation Center**
- **Physical Office Address**: `202 Robert Sobukwe Street, Esselen Towers, Sunnyside, Pretoria, 0002`
- **Consultation Pricing**: R450 consultation fee, R150 non-refundable booking deposit, balance of R300 due on arrival.
- **Operating Hours**:
  - Monday – Friday: 09:00 – 17:00
  - Saturday: 09:00 – 15:00
  - Sunday: Closed
- **Bank Account (EFT for Deposits)**:
  - Bank: First National Bank (FNB)
  - Account Name: NTOMBIKAYISE N MKHALIPHI
  - Account Number: `62804835835`
  - Branch Code: `250655`
  - Account Type: Cheque / Current Account
- **Social & Contact**:
  - Facebook: `https://www.facebook.com/share/1Cfx8cayqM/`
  - WhatsApp: `2785771853`

> [!IMPORTANT]
> **Host / Domain Constraint**:
> Never expose the local machine's Tailscale hostname (`1onsteenbok-jellyfin`) or the name "1onsteenbok" to Inner Health clients — that is for the user's guesthouse. Always use `innerhealth-consultation-center.onrender.com` or custom domain.

> [!NOTE]
> **Single Business Focus**:
> All other legacy pillars (Sound, IT, Driving, Beauty) were deliberately eradicated. Do not re-add them.

---

## 3. Architecture & Service Management

### Service Commands (Local Linux PC)
```bash
# Check status
sudo systemctl status inner-health

# Restart service after code changes
sudo systemctl restart inner-health

# Inspect live logs
sudo journalctl -u inner-health -f
```

### Git & Deployment Workflow
The local directory is connected to GitHub:
```bash
cd /home/washnet/business-dashboard
git status
git add -A
git commit -m "Your descriptive message"
git push origin main
```
Render automatically builds and deploys changes when pushed to `main` branch.

### Verifying Routes & Health
```bash
cd /home/washnet/business-dashboard
.venv/bin/python -c "import main; print('Total Routes:', len(main.app.routes))"
curl -s http://localhost:8000/api/health
```

---

## 4. Key Endpoints

- `GET /book` -> Public patient booking screen.
- `GET /` -> Admin Hub & client roster.
- `GET /admin/bookings` -> Scan Command Center & patient scan workflow.
- `GET /api/public/services` -> Active booking services list.
- `GET /api/public/config` -> Returns clinic metadata, WhatsApp, Facebook, and Office address.
- `GET /manage/{token}` -> Patient appointment management card.
- `GET /api/assistant/health` -> Local Ollama status (`http://127.0.0.1:11434`, model `llama3.2`).
