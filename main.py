"""
Inner Health Consultation Center — Scan Center & Booking Management
"""

import os
import re
import logging
import shutil
import subprocess
import tempfile
import uuid
import json
import secrets
import hashlib
import hmac
import base64
import time
import time as _time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, date, time
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Form, Depends, Header, Body, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, Boolean,
    DateTime, ForeignKey, Date, Time, UniqueConstraint, func, text, inspect, update
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from pydantic import BaseModel, field_validator, EmailStr, ConfigDict

# ---------------------------------------------------------------------------
# Timezone & Helpers
# ---------------------------------------------------------------------------

APP_TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Africa/Johannesburg"))

def app_now() -> datetime:
    return datetime.now(APP_TZ).replace(tzinfo=None)

def app_today() -> date:
    return app_now().date()

# ---------------------------------------------------------------------------
# Configuration & Database
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "business_hub.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{DB_PATH}"

connect_args = {}
engine_options = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    engine_options = {"pool_pre_ping": True}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **engine_options,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Single pillar: Inner Health
PILLARS: List[Dict[str, str]] = [
    {"id": "innerhealth", "name": "Inner Health", "icon": "🌿", "color": "#10b981",
     "desc": "Natural wellness consultations & supplements"},
]
PILLAR_IDS = [p["id"] for p in PILLARS]

DEFAULT_BATCH_PLAN: Dict[int, str] = {
    0: "innerhealth", 1: "innerhealth", 2: "innerhealth",
    3: "innerhealth", 4: "innerhealth", 5: "innerhealth", 6: "innerhealth",
}

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(40), nullable=True)
    phone_whatsapp = Column(String(40), nullable=True)
    email = Column(String(120), nullable=True)
    pillar = Column(String(40), nullable=True, default="innerhealth")
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(30), nullable=True)
    medical_notes = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=app_now)

    appointments = relationship("Appointment", back_populates="client", cascade="all, delete-orphan")
    contact_logs = relationship("ContactLog", back_populates="client", cascade="all, delete-orphan")


class PillarConfig(Base):
    __tablename__ = "pillar_configs"

    id = Column(Integer, primary_key=True, index=True)
    pillar = Column(String(40), unique=True, nullable=False)
    batch_day = Column(Integer, nullable=False, default=0)
    reminder_channel = Column(String(20), nullable=False, default="whatsapp")
    reminder_hours_before = Column(Integer, nullable=False, default=24)


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (UniqueConstraint("pillar", "date", "start_time", name="uq_pillar_slot"),)

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    pillar = Column(String(40), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=True)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=True)
    status = Column(String(20), nullable=False, default="scheduled")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=app_now)

    client = relationship("Client", back_populates="appointments")


class InventoryItem(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    pillar = Column(String(40), nullable=False, default="innerhealth")
    name = Column(String(120), nullable=False)
    category = Column(String(60), nullable=True)
    sku = Column(String(60), nullable=True)
    quantity = Column(Integer, nullable=False, default=0)
    reorder_level = Column(Integer, nullable=False, default=5)
    unit_price = Column(Float, nullable=True)
    supplier = Column(String(120), nullable=True)
    updated_at = Column(DateTime, default=app_now, onupdate=app_now)


class ContactLog(Base):
    __tablename__ = "contact_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    direction = Column(String(10), nullable=False, default="outbound")
    logged_at = Column(DateTime, default=app_now)

    client = relationship("Client", back_populates="contact_logs")


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    pillar = Column(String(40), nullable=False, default="innerhealth")
    description = Column(Text, nullable=False)
    amount = Column(Float, nullable=False, default=0.0)
    date = Column(Date, nullable=False, default=app_today)
    created_at = Column(DateTime, default=app_now)


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=True)
    channel = Column(String(20), nullable=False)
    send_at = Column(DateTime, nullable=False)
    scheduled_for = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    sent_at = Column(DateTime, nullable=True)
    message = Column(Text, nullable=False)
    recipient = Column(String(120), nullable=True)
    meta = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=app_now)


class CommandLog(Base):
    __tablename__ = "command_logs"

    id = Column(Integer, primary_key=True, index=True)
    raw = Column(Text, nullable=False)
    intent = Column(String(60), nullable=True)
    result = Column(Text, nullable=True)
    data = Column(Text, nullable=True)
    success = Column(Boolean, default=True)
    created_at = Column(DateTime, default=app_now)


class AppSetting(Base):
    """Small key/value store for things that must survive a redeploy (tokens, switches)."""
    __tablename__ = "app_settings"
    key = Column(String(80), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=app_now, onupdate=app_now)


class AgentDocument(Base):
    """Anything uploaded to the agent or generated by it (PDFs, scans, reports)."""
    __tablename__ = "agent_documents"

    id = Column(Integer, primary_key=True)
    doc_id = Column(String(40), unique=True, nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="upload")   # upload | report
    title = Column(String(240), nullable=True)
    filename = Column(String(240), nullable=False)
    path = Column(String(500), nullable=False)
    mime = Column(String(120), nullable=True)
    size = Column(Integer, default=0)
    extracted_text = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    booking_id = Column(Integer, nullable=True)
    session_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=app_now)


class AgentConversation(Base):
    """Long-lived memory for the admin agent: one row per chat thread."""
    __tablename__ = "agent_conversations"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    title = Column(String(200), nullable=True)
    summary = Column(Text, nullable=True)          # rolling summary of older turns
    facts = Column(Text, nullable=True)            # JSON list of durable things learned
    turn_count = Column(Integer, nullable=False, default=0)
    last_active = Column(DateTime, default=app_now)
    created_at = Column(DateTime, default=app_now)


class AgentMessage(Base):
    """Every turn in every admin-agent conversation, newest last."""
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(64), nullable=False, index=True)
    role = Column(String(16), nullable=False)      # user | assistant
    content = Column(Text, nullable=False)
    mode = Column(String(16), nullable=True)       # rules | model | voice
    created_at = Column(DateTime, default=app_now)


class BookingService(Base):
    __tablename__ = "booking_services"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, default="")
    duration_minutes = Column(Integer, nullable=False, default=45)
    price = Column(Float, nullable=False, default=450)
    deposit = Column(Float, nullable=False, default=150)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=app_now)


class AvailabilityRule(Base):
    __tablename__ = "availability_rules"
    id = Column(Integer, primary_key=True)
    day_of_week = Column(Integer, nullable=False, unique=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    is_working_day = Column(Boolean, nullable=False, default=False)


class BlockedDate(Base):
    __tablename__ = "blocked_dates"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True)
    reason = Column(String(240), default="")


class PublicBooking(Base):
    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("booking_date", "start_time", name="uq_public_booking_slot"),)
    id = Column(Integer, primary_key=True)
    booking_ref = Column(String(40), unique=True, nullable=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("booking_services.id"), nullable=False)
    booking_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(String(20), nullable=False, default="pending_deposit")
    total_fee = Column(Float, nullable=False, default=450.0)
    deposit_paid = Column(Float, nullable=False, default=0.0)
    balance_due = Column(Float, nullable=False, default=450.0)
    balance_paid = Column(Boolean, nullable=False, default=False)
    payment_method_balance = Column(String(20), nullable=False, default="unpaid")
    ai_scan_status = Column(String(40), nullable=False, default="not_started")
    ai_scan_input = Column(Text, nullable=True)
    ai_scan_report = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    reminder_24h_sent = Column(Boolean, nullable=False, default=False)
    reminder_2h_sent = Column(Boolean, nullable=False, default=False)
    # Proof of payment the guest attached after booking (filename in uploads/proofs)
    payment_proof = Column(String(160), nullable=True)
    proof_uploaded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=app_now)

    client = relationship("Client")
    service = relationship("BookingService")


class WalkInSale(Base):
    __tablename__ = "walk_in_sales"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    item_name = Column(String(140), nullable=False)
    amount_zar = Column(Float, nullable=False)
    payment_method = Column(String(20), nullable=False, default="cash")
    sold_at = Column(DateTime, default=app_now)


class AIAgentHeartbeat(Base):
    __tablename__ = "ai_agent_heartbeats"
    id = Column(Integer, primary_key=True)
    model = Column(String(80), nullable=False)
    last_seen = Column(DateTime, nullable=False, default=app_now)


class AdminCredential(Base):
    __tablename__ = "admin_credentials"
    id = Column(Integer, primary_key=True)
    password_hash = Column(String(128), nullable=False)
    password_salt = Column(String(64), nullable=False)
    updated_at = Column(DateTime, default=app_now)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class AdminPasswordChange(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("new password must be at least 12 characters")
        return v

class ClientCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    pillar: Optional[str] = "innerhealth"
    notes: Optional[str] = None

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    pillar: Optional[str] = None
    notes: Optional[str] = None

class AppointmentCreate(BaseModel):
    title: str
    pillar: str = "innerhealth"
    client_id: Optional[int] = None
    date: date
    start_time: time
    end_time: Optional[time] = None
    notes: Optional[str] = None

class InventoryCreate(BaseModel):
    pillar: str = "innerhealth"
    name: str
    category: Optional[str] = None
    sku: Optional[str] = None
    quantity: int = 0
    reorder_level: int = 5
    unit_price: Optional[float] = None
    supplier: Optional[str] = None

class ContactLogCreate(BaseModel):
    client_id: int
    channel: str
    message: str
    direction: str = "outbound"

class ServiceRecordCreate(BaseModel):
    client_id: Optional[int] = None
    pillar: str = "innerhealth"
    description: str
    amount: float = 0.0
    date: Optional[date] = None

class PillarConfigUpdate(BaseModel):
    batch_day: int
    reminder_channel: str
    reminder_hours_before: int

class CommandRequest(BaseModel):
    command: str

class AssistantRequest(BaseModel):
    message: str
    history: List[Dict[str, Any]] = []

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Inner Health Consultation Center",
    description="Scan Center bookings, client management & local AI assistance",
    version="2.0.0",
)

templates = Jinja2Templates(directory=STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Event bus: push state changes to every open dashboard over Server-Sent Events
# ---------------------------------------------------------------------------

import asyncio
import queue
import threading


class EventBus:
    """Fan-out broadcast of state-change events to all connected SSE clients.

    Publishers may be called from sync request handlers, so publish() is
    thread-safe: it puts the event on per-subscriber queues, and each SSE
    generator (an asyncio task) drains its own queue.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[int, "queue.Queue[dict]"] = {}
        self._lock = threading.Lock()
        self._seq = 0
        self.last_event: Dict[str, Any] = {"type": "boot", "at": app_now().isoformat(timespec="seconds")}

    def subscribe(self) -> tuple:
        with self._lock:
            self._seq += 1
            sid = self._seq
            q: "queue.Queue[dict]" = queue.Queue(maxsize=200)
            self._subscribers[sid] = q
        return sid, q

    def unsubscribe(self, sid: int) -> None:
        with self._lock:
            self._subscribers.pop(sid, None)

    def publish(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        event = {
            "type": event_type,
            "at": app_now().isoformat(timespec="seconds"),
            "data": payload or {},
        }
        self.last_event = event
        with self._lock:
            targets = list(self._subscribers.values())
        for q in targets:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # slow client: drop rather than block the request

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


events = EventBus()


def emit(event_type: str, **payload) -> None:
    """Shorthand for events.publish used across request handlers."""
    try:
        events.publish(event_type, payload)
    except Exception:
        pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

_WHISPER_MODEL = None


def _warm_whisper() -> None:
    """Load the speech model in the background so the first voice note is fast."""
    global _WHISPER_MODEL
    try:
        from faster_whisper import WhisperModel  # type: ignore
        _WHISPER_MODEL = WhisperModel(
            os.getenv("WHISPER_MODEL", "base"),
            device="cpu", compute_type="int8",
            cpu_threads=max(2, os.cpu_count() or 2),
        )
        logging.getLogger("uvicorn.error").info("whisper model warmed up")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("uvicorn.error").warning("whisper not available: %s", exc)


def _keep_warm():
    """Ping our own public URL so the free instance does not fall asleep.

    Render's free plan spins down after about 15 minutes without traffic, and the next
    visitor waits 30 to 50 seconds. A ping every 10 minutes keeps it awake, so the
    dashboard opens immediately on the phone. Pings stop when this process stops,
    so it costs nothing when the app is already running somewhere else.
    """
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base or os.getenv("KEEP_WARM", "1") == "0":
        return
    url = base + "/api/health"
    # Skip when this is the local install: it would just keep waking the cloud copy
    if "127.0.0.1" in base or "localhost" in base:
        return
    _time.sleep(60)  # let the app finish starting before the first ping
    while True:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "inner-health-keepwarm"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
        except Exception:
            pass
        _time.sleep(600)  # every 10 minutes, comfortably inside Render's idle window


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _seed_defaults()
    threading.Thread(target=_warm_whisper, daemon=True).start()
    threading.Thread(target=_keep_warm, daemon=True).start()

def _seed_defaults():
    db = SessionLocal()
    try:
        for p in PILLARS:
            cfg = db.query(PillarConfig).filter(PillarConfig.pillar == p["id"]).first()
            if not cfg:
                db.add(PillarConfig(
                    pillar=p["id"],
                    batch_day=0,
                    reminder_channel="whatsapp",
                    reminder_hours_before=24,
                ))
        if db.query(BookingService).count() == 0:
            db.add_all([
                BookingService(name="Full-body scan consultation", description="Full-body scan and consultation with an individual results review.", duration_minutes=45, price=450, deposit=150),
                BookingService(name="Follow up scan", description="Follow-up scan consultation and progress review.", duration_minutes=45, price=450, deposit=150),
            ])
        db.query(BookingService).filter(BookingService.name.like("%Wellness report%")).delete(synchronize_session=False)
        if db.query(AvailabilityRule).count() == 0:
            for weekday in range(7):
                working = weekday < 6
                db.add(AvailabilityRule(day_of_week=weekday, is_working_day=working,
                                        start_time=time(9) if working else None,
                                        end_time=(time(15) if weekday == 5 else time(17)) if working else None))
        db.commit()
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Security & Auth
# ---------------------------------------------------------------------------

security = HTTPBasic(auto_error=False)

def _admin_password_matches(password: str) -> bool:
    db = SessionLocal()
    try:
        saved = db.query(AdminCredential).filter_by(id=1).first()
        if saved:
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(saved.password_salt), 310_000).hex()
            return hmac.compare_digest(candidate, saved.password_hash)
        configured = os.getenv("ADMIN_PASSWORD", "")
        return bool(configured) and hmac.compare_digest(password, configured)
    finally:
        db.close()

def require_admin(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    # Password requirement temporarily disabled per user request
    return True

def require_ai_agent(x_ai_agent_key: str = Header(default="")):
    expected = os.getenv("AI_AGENT_KEY", "")
    if expected and not hmac.compare_digest(x_ai_agent_key, expected):
        raise HTTPException(401, "invalid AI agent key")
    return True

# ---------------------------------------------------------------------------
# Booking Helpers
# ---------------------------------------------------------------------------

def find_conflicts(db: Session, pillar: str, appt_date: date,
                   start: time, end: Optional[time], exclude_id: Optional[int] = None) -> List[Appointment]:
    end = end or (datetime.combine(appt_date, start) + timedelta(hours=1)).time()
    query = db.query(Appointment).filter(
        Appointment.date == appt_date,
        Appointment.status != "cancelled",
    )
    if exclude_id is not None:
        query = query.filter(Appointment.id != exclude_id)
    conflicts = []
    for a in query.all():
        a_end = a.end_time or (datetime.combine(a.date, a.start_time) + timedelta(hours=1)).time()
        if start < a_end and end > a.start_time:
            conflicts.append(a)
    return conflicts

def _active_overlap(db: Session, day: date, start: time, end: time, exclude: Optional[int] = None) -> bool:
    for b in db.query(PublicBooking).filter(PublicBooking.booking_date == day,
            PublicBooking.status.in_(["pending_deposit", "confirmed", "arriving_soon", "in_scan"])).all():
        if b.id != exclude and start < b.end_time and end > b.start_time:
            return True
    for a in db.query(Appointment).filter(Appointment.date == day, Appointment.status != "cancelled").all():
        a_end = a.end_time or (datetime.combine(day, a.start_time) + timedelta(hours=1)).time()
        if start < a_end and end > a.start_time:
            return True
    return False

def _lock_booking_day(db: Session, day: date):
    if engine.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:day))"), {"day": day.isoformat()})
    else:
        db.execute(update(AvailabilityRule).where(AvailabilityRule.day_of_week == day.weekday())
                   .values(is_working_day=AvailabilityRule.is_working_day))

def _slots(db: Session, day: date, service: BookingService, exclude_booking_id: Optional[int] = None) -> List[str]:
    rule = db.query(AvailabilityRule).filter_by(day_of_week=day.weekday()).first()
    if not rule or not rule.is_working_day or not rule.start_time or not rule.end_time:
        return []
    if db.query(BlockedDate).filter_by(date=day).first():
        return []
    
    slots = []
    cursor = datetime.combine(day, rule.start_time)
    end_limit = datetime.combine(day, rule.end_time)
    now = app_now()

    while cursor + timedelta(minutes=service.duration_minutes) <= end_limit:
        slot_start = cursor.time()
        slot_end = (cursor + timedelta(minutes=service.duration_minutes)).time()
        if (day > app_today() or cursor > now) and not _active_overlap(db, day, slot_start, slot_end, exclude=exclude_booking_id):
            slots.append(cursor.strftime("%H:%M"))
        cursor += timedelta(minutes=30)
    return slots

def _manage_token(booking_id: int) -> str:
    key = os.getenv("BOOKING_TOKEN_SECRET") or os.getenv("ADMIN_PASSWORD") or "inner-health-secret"
    return hmac.new(key.encode(), f"booking:{booking_id}".encode(), hashlib.sha256).hexdigest()

def _deposit_checkout_url(booking: PublicBooking, token: str) -> Optional[str]:
    url = os.getenv("DEPOSIT_CHECKOUT_URL", "")
    if not url:
        return None
    origin = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}reference={booking.booking_ref}&amount={booking.service.deposit}&return_url={origin}/manage/{token}"

def _bank_transfer_details(booking_ref: str, amount: float) -> Dict[str, str]:
    return {
        "account_name": os.getenv("BANK_ACCOUNT_NAME", "NTOMBIKAYISE N MKHALIPHI"),
        "bank": os.getenv("BANK_NAME", "FNB"),
        "account_number": os.getenv("BANK_ACCOUNT_NUMBER", "62804835835"),
        "branch_code": os.getenv("BANK_BRANCH_CODE", "250655"),
        "account_type": os.getenv("BANK_ACCOUNT_TYPE", "Cheque"),
        "reference": booking_ref,
        "amount_zar": f"{amount:.2f}",
        "instructions": "Use your reference when transferring funds. Send proof of payment via WhatsApp."
    }

def _notify(client: Client, service: BookingService, when: datetime, token: str):
    origin = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    link = f"{origin}/manage/{token}"
    message = f"Your {service.name} appointment is booked for {when:%A, %d %B %Y at %H:%M}. Manage it: {link}"
    if client.email:
        _send_email(client.email, "Inner Health appointment confirmation", message)

    hook = os.getenv("WHATSAPP_WEBHOOK_URL")
    if hook and (client.phone_whatsapp or client.phone):
        phone_to = client.phone_whatsapp or client.phone
        try:
            req = urllib.request.Request(hook, data=json.dumps({"to": phone_to, "message": message}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8).read()
        except Exception as exc:
            print(f"WhatsApp webhook failed: {exc}")

# ---------------------------------------------------------------------------
# Meta & Management APIs
# ---------------------------------------------------------------------------

@app.get("/api/pillars")
def get_pillars():
    return {"pillars": PILLARS, "days": WEEKDAYS}

@app.get("/api/pillar-configs")
def get_pillar_configs(db: Session = Depends(get_db)):
    cfgs = db.query(PillarConfig).all()
    return {c.pillar: {
        "batch_day": c.batch_day,
        "reminder_channel": c.reminder_channel,
        "reminder_hours_before": c.reminder_hours_before,
    } for c in cfgs}

@app.put("/api/pillar-configs/{pillar}")
def update_pillar_config(pillar: str, payload: PillarConfigUpdate, db: Session = Depends(get_db)):
    cfg = db.query(PillarConfig).filter_by(pillar=pillar).first()
    if not cfg:
        cfg = PillarConfig(pillar=pillar, **payload.model_dump())
        db.add(cfg)
    else:
        for k, v in payload.model_dump().items():
            setattr(cfg, k, v)
    db.commit()
    emit("pillar.updated")
    return {"status": "ok"}

@app.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    today = app_today()
    total_clients = db.query(Client).count()
    today_appts = db.query(Appointment).filter(Appointment.date == today).all()
    today_bookings = db.query(PublicBooking).filter(PublicBooking.booking_date == today).all()
    upcoming_appts = db.query(Appointment).filter(Appointment.date >= today).order_by(Appointment.date, Appointment.start_time).limit(10).all()
    return {
        "today": today.isoformat(),
        "total_clients": total_clients,
        "today_appointments_count": len(today_appts) + len(today_bookings),
        "upcoming_appointments": [
            {"id": a.id, "title": a.title, "pillar": a.pillar, "date": a.date.isoformat(),
             "start_time": a.start_time.strftime("%H:%M"), "status": a.status,
             "client_name": a.client.name if a.client else None}
            for a in upcoming_appts
        ],
    }

@app.get("/api/clients")
def list_clients(pillar: Optional[str] = None, search: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Client)
    if search:
        like = f"%{search}%"
        q = q.filter((Client.name.ilike(like)) | (Client.phone.ilike(like)) | (Client.email.ilike(like)))
    clients = q.order_by(Client.name).all()
    return [
        {
            "id": c.id, "name": c.name, "full_name": c.name, "phone": c.phone_whatsapp or c.phone, "phone_whatsapp": c.phone_whatsapp or c.phone, "email": c.email,
            "pillar": c.pillar, "notes": c.notes,
            "appointment_count": len(c.appointments),
            "booking_count": db.query(func.count(PublicBooking.id)).filter(PublicBooking.client_id == c.id).scalar(),
            "service_count": db.query(func.count(ServiceRecord.id)).filter(ServiceRecord.client_id == c.id).scalar(),
        }
        for c in clients
    ]

@app.post("/api/clients", status_code=201)
def create_client(payload: ClientCreate, db: Session = Depends(get_db)):
    c = Client(**payload.model_dump())
    c.phone_whatsapp = c.phone
    db.add(c)
    db.commit()
    emit("client.created", name=getattr(client, "name", None))
    db.refresh(c)
    return {"id": c.id, "name": c.name}

@app.get("/api/clients/{client_id}")
def get_client(client_id: int, db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(404, "client not found")
    return {
        "id": c.id, "name": c.name, "phone": c.phone_whatsapp or c.phone, "phone_whatsapp": c.phone_whatsapp or c.phone, "email": c.email,
        "pillar": c.pillar, "notes": c.notes, "medical_notes": c.medical_notes,
        "date_of_birth": c.date_of_birth.isoformat() if c.date_of_birth else None, "gender": c.gender,
        "appointments": [
            {"id": a.id, "title": a.title, "date": a.date.isoformat(), "start_time": a.start_time.strftime("%H:%M"), "status": a.status}
            for a in c.appointments
        ],
        "bookings": [
            {"id": b.id, "reference": b.booking_ref, "service": b.service.name, "date": b.booking_date.isoformat(), "start_time": b.start_time.strftime("%H:%M"), "status": b.status}
            for b in db.query(PublicBooking).filter_by(client_id=c.id).all()
        ]
    }

@app.put("/api/clients/{client_id}")
def update_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(404, "client not found")
    data = payload.model_dump(exclude_unset=True)
    if "phone" in data and not data.get("phone_whatsapp"):
        data["phone_whatsapp"] = data["phone"]
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    emit("client.updated")
    return {"id": c.id, "name": c.name}

@app.delete("/api/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(404, "client not found")
    db.delete(c)
    db.commit()
    emit("client.deleted")
    return {"ok": True}

@app.get("/api/appointments")
def list_appointments(week_start: Optional[date] = None, pillar: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Appointment)
    if week_start:
        q = q.filter(Appointment.date >= week_start, Appointment.date < week_start + timedelta(days=7))
    appts = q.order_by(Appointment.date, Appointment.start_time).all()
    return [
        {"id": a.id, "title": a.title, "pillar": a.pillar, "date": a.date.isoformat(),
         "start_time": a.start_time.strftime("%H:%M"), "end_time": a.end_time.strftime("%H:%M") if a.end_time else None,
         "status": a.status, "notes": a.notes, "client_id": a.client_id, "client_name": a.client.name if a.client else None}
        for a in appts
    ]

@app.post("/api/appointments", status_code=201)
def create_appointment(payload: AppointmentCreate, db: Session = Depends(get_db)):
    end_time = payload.end_time or (datetime.combine(payload.date, payload.start_time) + timedelta(hours=1)).time()
    appt = Appointment(**payload.model_dump(exclude={"end_time"}), end_time=end_time)
    db.add(appt)
    db.commit()
    emit("appointment.created")
    db.refresh(appt)
    return {"id": appt.id, "title": appt.title}

@app.put("/api/appointments/{appt_id}")
def update_appointment(appt_id: int, payload: AppointmentCreate, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not a:
        raise HTTPException(404, "appointment not found")
    for k, v in payload.model_dump().items():
        setattr(a, k, v)
    db.commit()
    emit("appointment.updated")
    return {"id": a.id}

@app.patch("/api/appointments/{appt_id}/status")
def patch_appointment_status(appt_id: int, status: str, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not a:
        raise HTTPException(404, "appointment not found")
    a.status = status
    db.commit()
    emit("appointment.status")
    return {"id": a.id, "status": a.status}

@app.delete("/api/appointments/{appt_id}")
def delete_appointment(appt_id: int, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not a:
        raise HTTPException(404, "appointment not found")
    db.delete(a)
    db.commit()
    emit("appointment.deleted")
    return {"ok": True}

@app.get("/api/inventory")
def list_inventory(pillar: Optional[str] = None, low_stock: bool = False, db: Session = Depends(get_db)):
    q = db.query(InventoryItem)
    if low_stock:
        q = q.filter(InventoryItem.quantity <= InventoryItem.reorder_level)
    items = q.order_by(InventoryItem.name).all()
    return [
        {"id": i.id, "name": i.name, "pillar": i.pillar, "category": i.category, "sku": i.sku,
         "quantity": i.quantity, "reorder_level": i.reorder_level, "unit_price": i.unit_price,
         "supplier": i.supplier, "low": i.quantity <= i.reorder_level}
        for i in items
    ]

@app.post("/api/inventory", status_code=201)
def create_inventory(payload: InventoryCreate, db: Session = Depends(get_db)):
    item = InventoryItem(**payload.model_dump())
    db.add(item)
    db.commit()
    emit("inventory.created")
    db.refresh(item)
    return {"id": item.id, "name": item.name}

@app.put("/api/inventory/{item_id}")
def update_inventory(item_id: int, payload: InventoryCreate, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    for k, v in payload.model_dump().items():
        setattr(item, k, v)
    db.commit()
    emit("inventory.updated")
    return {"id": item.id}

@app.patch("/api/inventory/{item_id}/adjust")
def adjust_inventory(item_id: int, delta: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    item.quantity = max(0, item.quantity + delta)
    db.commit()
    emit("inventory.updated")
    return {"id": item.id, "quantity": item.quantity, "low": item.quantity <= item.reorder_level}

@app.delete("/api/inventory/{item_id}")
def delete_inventory(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    db.delete(item)
    db.commit()
    emit("inventory.deleted")
    return {"ok": True}

@app.post("/api/contact-logs", status_code=201)
def create_contact_log(payload: ContactLogCreate, db: Session = Depends(get_db)):
    log = ContactLog(**payload.model_dump())
    db.add(log)
    db.commit()
    emit("contact.logged")
    db.refresh(log)
    return {"id": log.id}

@app.post("/api/service-records", status_code=201)
def create_service_record(payload: ServiceRecordCreate, db: Session = Depends(get_db)):
    s = ServiceRecord(**payload.model_dump())
    db.add(s)
    db.commit()
    emit("service.logged")
    db.refresh(s)
    return {"id": s.id}

@app.get("/api/reminders")
def list_reminders(db: Session = Depends(get_db)):
    rems = db.query(Reminder).order_by(Reminder.send_at.desc()).limit(20).all()
    return [{"id": r.id, "appointment_id": r.appointment_id, "channel": r.channel, "send_at": r.send_at.isoformat(), "status": r.status, "message": r.message} for r in rems]

@app.get("/api/events")
async def event_stream(request: Request):
    """Server-Sent Events stream. Every dashboard opens one and stays connected.

    The browser receives a `state` event the moment anything changes, so the
    admin UI never polls. A heartbeat comment every 20s keeps proxies and
    mobile networks from closing the connection.
    """

    async def generator():
        sid, q = events.subscribe()
        try:
            yield "retry: 3000\n\n"
            yield f"event: ready\ndata: {json.dumps({'connected_at': app_now().isoformat(timespec='seconds'), 'clients': events.client_count})}\n\n"
            last = events.last_event
            if last:
                yield f"event: state\ndata: {json.dumps(last)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.to_thread(q.get, True, 20)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: state\ndata: {json.dumps(event)}\n\n"
        finally:
            events.unsubscribe(sid)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/events/status")
def event_status():
    return {"clients": events.client_count, "last_event": events.last_event}


@app.post("/api/events/ping", dependencies=[Depends(require_admin)])
def event_ping():
    emit("ping", source="admin")
    return {"ok": True, "clients": events.client_count}


@app.get("/api/reminders/generate", dependencies=[Depends(require_admin)])
def reminders_generate_get():
    return {"detail": "Use POST with an optional JSON body: hours_ahead, dry_run, include_deposits, include_balances, include_winback"}


@app.post("/api/reminders/generate", dependencies=[Depends(require_admin)])
async def generate_reminders(payload: dict = Body(default={}), db: Session = Depends(get_db)):
    """Generate smart reminders using AI. Creates reminder records for upcoming bookings."""
    today = app_today()
    now = app_now()
    hours_ahead = int(payload.get("hours_ahead", 30))
    include_deposits = payload.get("include_deposits", True)
    include_balances = payload.get("include_balances", True)
    include_winback = payload.get("include_winback", False)
    dry_run = payload.get("dry_run", False)

    bookings = db.query(PublicBooking).filter(
        PublicBooking.status.in_(("confirmed", "arriving_soon", "pending_deposit")),
        PublicBooking.booking_date >= today
    ).all()

    clinic_name = "Inner Health Consultation Center"
    clinic_addr = os.getenv("CLINIC_ADDRESS", "202 Robert Sobukwe Street, Esselen Towers, Sunnyside, Pretoria, 0002")
    wa_number = os.getenv("WHATSAPP_NUMBER", "2785771853")
    email_addr = os.getenv("CLINIC_EMAIL", "innerhealthconsult@gmail.com")

    created = 0
    skipped = 0

    for b in bookings:
        when = datetime.combine(b.booking_date, b.start_time)
        hours_until = (when - now).total_seconds() / 3600
        if hours_until <= 0 or hours_until > hours_ahead:
            continue

        client = b.client
        phone = client.phone_whatsapp or client.phone
        first_name = (client.name or "").split()[0]

        # Deposit reminder
        if include_deposits and b.status == "pending_deposit":
            existing = db.query(Reminder).filter(
                Reminder.appointment_id == b.id,
                Reminder.channel == "whatsapp",
                Reminder.message.like(f"%deposit%{b.booking_ref}%")
            ).first()
            if not existing:
                msg = await _ai_reminder_text(db, {
                    "type": "deposit",
                    "first_name": first_name,
                    "date": b.booking_date.strftime("%A %d %B"),
                    "time": b.start_time.strftime("%H:%M"),
                    "deposit": b.service.deposit,
                    "ref": b.booking_ref,
                    "clinic": clinic_name,
                    "address": clinic_addr,
                    "bank": {"name": "FNB", "account": "Ntombikayise N Mkhaliphi", "number": "62804835835", "branch": "250655"}
                })
                if not dry_run:
                    rem = Reminder(
                        appointment_id=b.id, pillar="innerhealth", channel="whatsapp",
                        recipient=phone, message=msg, scheduled_for=now, status="pending"
                    )
                    db.add(rem)
                created += 1
            else:
                skipped += 1

        # 24h / 2h appointment reminder
        if b.status in ("confirmed", "arriving_soon"):
            for window, label in [(24, "24h"), (2, "2h")]:
                if abs(hours_until - window) <= 1.5:  # within 90 min of target
                    existing = db.query(Reminder).filter(
                        Reminder.appointment_id == b.id,
                        Reminder.channel == "whatsapp",
                        Reminder.message.like(f"%{label}%{b.booking_ref}%")
                    ).first()
                    if not existing:
                        msg = await _ai_reminder_text(db, {
                            "type": "appointment",
                            "first_name": first_name,
                            "date": b.booking_date.strftime("%A %d %B"),
                            "time": b.start_time.strftime("%H:%M"),
                            "balance": b.balance_due if not b.balance_paid else 0,
                            "ref": b.booking_ref,
                            "clinic": clinic_name,
                            "address": clinic_addr
                        })
                        if not dry_run:
                            rem = Reminder(
                                appointment_id=b.id, pillar="innerhealth", channel="whatsapp",
                                recipient=phone, message=msg, scheduled_for=now, status="pending"
                            )
                            db.add(rem)
                        created += 1
                    else:
                        skipped += 1

    # Win-back reminders for lapsed clients
    if include_winback:
        snapshot = _admin_snapshot(db)
        for row in snapshot["clients"]["lapsed_list"][:20]:
            existing = db.query(Reminder).filter(
                Reminder.recipient == row["phone"],
                Reminder.channel == "whatsapp",
                Reminder.message.like(f"%{clinic_name}%{row['name']}%"),
                Reminder.created_at >= now - timedelta(days=7)
            ).first()
            if not existing:
                msg = await _ai_reminder_text(db, {
                    "type": "winback",
                    "first_name": row["name"].split()[0],
                    "days_since": row["days_since"],
                    "clinic": clinic_name,
                    "whatsapp": wa_number
                })
                if not dry_run:
                    rem = Reminder(
                        appointment_id=None, pillar="innerhealth", channel="whatsapp",
                        recipient=row["phone"], message=msg, scheduled_for=now, status="pending"
                    )
                    db.add(rem)
                created += 1
            else:
                skipped += 1

    if not dry_run:
        db.commit()
    return {"created": created, "skipped": skipped, "dry_run": dry_run}


@app.post("/api/reminders/send-all", dependencies=[Depends(require_admin)])
def send_all_reminders(db: Session = Depends(get_db)):
    """Send all pending reminders via WhatsApp (creates wa.me links) and email if configured."""
    now = app_now()
    pending = db.query(Reminder).filter(Reminder.status == "pending").all()
    sent = 0
    failed = 0
    for r in pending:
        try:
            wa_link = f"https://wa.me/{re.sub(r'[^0-9]', '', r.recipient or '')}?text={urllib.parse.quote(r.message)}"
            # Log the send
            r.status = "sent"
            r.sent_at = now
            r.meta = json.dumps({"wa_link": wa_link})
            sent += 1
        except Exception as e:
            r.status = "failed"
            r.error = str(e)
            failed += 1
    db.commit()
    emit("reminders.sent")
    return {"sent": sent, "failed": failed, "total": len(pending)}


async def _ai_reminder_text(db: Session, ctx: dict) -> str:
    """Use the local admin model to craft a warm, concise reminder."""
    try:
        system = (
            "You write short, warm WhatsApp reminders for Inner Health Consultation Center, Pretoria. "
            "Max 2 sentences. No markdown. Include the reference number. Sound human, not robotic."
        )
        user = json.dumps(ctx, ensure_ascii=False)
        body = json.dumps({
            "model": ADMIN_MODEL,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False, "keep_alive": "10m",
            "options": {"temperature": 0.3, "num_predict": 160}
        }).encode()
        for base, _ in _ollama_backends():
            try:
                req = urllib.request.Request(base + "/api/chat", data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read())
                txt = _clean_reply(data.get("message", {}).get("content", ""))
                if len(txt) > 20:
                    return txt
            except Exception:
                continue
    except Exception:
        pass
    # Fallback templates
    if ctx.get("type") == "deposit":
        return f"Hi {ctx['first_name']}, your {ctx['clinic']} scan on {ctx['date']} at {ctx['time']} needs the R{int(ctx['deposit'])} deposit to confirm. Ref {ctx['ref']}. FNB: {ctx['bank']['account']}, {ctx['bank']['number']}, branch {ctx['bank']['branch']}."
    if ctx.get("type") == "appointment":
        bal = f" Balance R{int(ctx['balance'])} due." if ctx.get('balance') else ""
        return f"Hi {ctx['first_name']}, reminder: your scan is {ctx['date']} at {ctx['time']} at {ctx['address']}. Ref {ctx['ref']}.{bal}"
    if ctx.get("type") == "winback":
        return f"Hi {ctx['first_name']}, it's been {ctx['days_since']} days since your last scan with {ctx['clinic']}. Want to book again? Reply here or WhatsApp {ctx['whatsapp']}."
    return "Reminder from Inner Health Consultation Center."

@app.post("/api/command")
def process_command(payload: CommandRequest, db: Session = Depends(get_db)):
    raw = payload.command.strip()
    return {"raw": raw, "intent": "general", "message": f"Processed: {raw}", "data": None}

# ---------------------------------------------------------------------------
# Assistant (local lightweight Ollama model, clinic-grounded)
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_MODEL = "ihc-qwen3-4b"


def _ollama_backends() -> List[tuple]:
    """Ordered (url, model) pairs. The Mac mini primary is skipped while it is unreachable."""
    pairs = [
        (os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"), os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)),
        (os.getenv("OLLAMA_FALLBACK_BASE_URL", "http://127.0.0.1:11434").rstrip("/"), os.getenv("OLLAMA_FALLBACK_MODEL", DEFAULT_OLLAMA_MODEL)),
    ]
    seen, unique = set(), []
    for url, model in pairs:
        if (url, model) not in seen:
            seen.add((url, model))
            unique.append((url, model))
    return unique


def _assistant_facts(db: Session) -> Dict[str, Any]:
    """Live clinic facts so the small model never has to guess."""
    services = []
    for s in db.query(BookingService).filter_by(is_active=True).all():
        services.append({"id": s.id, "name": s.name, "minutes": s.duration_minutes,
                         "price": s.price, "deposit": s.deposit})
    hours = []
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for rule in db.query(AvailabilityRule).order_by(AvailabilityRule.day_of_week).all():
        label = names[rule.day_of_week] if 0 <= rule.day_of_week < 7 else str(rule.day_of_week)
        if rule.is_working_day and rule.start_time and rule.end_time:
            hours.append(f"{label} {rule.start_time.strftime('%H:%M')}-{rule.end_time.strftime('%H:%M')}")
        else:
            hours.append(f"{label} closed")
    return {"services": services, "hours": hours}


def _public_service(db: Session) -> Optional[BookingService]:
    return db.query(BookingService).filter_by(is_active=True).order_by(BookingService.id).first()


def _next_open_slots(db: Session, service: Optional[BookingService], days: int = 10) -> Dict[str, List[str]]:
    if not service:
        return {}
    found: Dict[str, List[str]] = {}
    for offset in range(days):
        day = app_today() + timedelta(days=offset)
        slots = _slots(db, day, service)[:4]
        if slots:
            found[day.isoformat()] = slots
        if len(found) >= 3:
            break
    return found


def _assistant_system_prompt(db: Session) -> tuple:
    facts = _assistant_facts(db)
    service = _public_service(db)
    slots = _next_open_slots(db, service)
    money = lambda v: f"R{int(round(float(v or 0)))}"
    lines = [
        "You are the booking assistant for Inner Health Consultation Center, a wellness scan clinic in Sunnyside, Pretoria, South Africa.",
        "Style: warm, plain, short. Two or three sentences at most. No markdown, no lists unless asked for the full price list.",
        f"Address: {os.getenv('CLINIC_ADDRESS', '202 Robert Sobukwe Street, Esselen Towers, Sunnyside, Pretoria, 0002')}.",
        f"WhatsApp: +{os.getenv('WHATSAPP_NUMBER', '2785771853')}. Email: {os.getenv('CLINIC_EMAIL', 'innerhealthconsult@gmail.com')}. Booking page: /book",
        "Services and prices: " + "; ".join(
            f"{s['name']} {money(s['price'])} for {s['minutes']} minutes, {money(s['deposit'])} non-refundable deposit and the rest on arrival"
            for s in facts["services"]),
        "Opening hours: " + ", ".join(facts["hours"]) + ".",
        "Deposits are paid by EFT: FNB, account name Ntombikayise N Mkhaliphi, account 62804835835, branch 250655, cheque account. Reply with the reference we give them.",
    ]
    lines.append("We also stock the Green World natural health range in store: " + _product_summary_line() + ".")
    lines += _product_knowledge_lines()
    if slots:
        lines.append("Next open scan slots: " + "; ".join(f"{d} at {', '.join(v)}" for d, v in slots.items()) + ".")
    lines += [
        "Rules you must never break: you are not a doctor, you do not diagnose disease, prescribe medicine, interpret scan results or promise a cure. For anything clinical say the scan is reviewed with a qualified practitioner at the consultation.",
        "If asked something you do not know about the clinic, say you will have the team confirm on WhatsApp rather than inventing it.",
        "Only Inner Health matters. If asked about anything unrelated, gently bring the conversation back to booking a scan.",
        "Never promise a slot until the booking page confirms it: always send them to /book to pick a time.",
    ]
    return "\n".join(lines), slots


# ---------------------------------------------------------------------------
# Product catalog (Green World range, loaded from static/products/catalog.json)
# ---------------------------------------------------------------------------

PRODUCTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "products", "catalog.json")
_PRODUCTS_CACHE: Dict[str, Any] = {"mtime": None, "items": []}


def _products() -> List[Dict[str, Any]]:
    """Load and cache the product catalog, reloading when the file changes."""
    try:
        mtime = os.path.getmtime(PRODUCTS_FILE)
    except OSError:
        return []
    if _PRODUCTS_CACHE["mtime"] != mtime:
        try:
            with open(PRODUCTS_FILE, "r", encoding="utf-8") as fh:
                items = json.load(fh)
            _PRODUCTS_CACHE["items"] = items if isinstance(items, list) else []
            _PRODUCTS_CACHE["mtime"] = mtime
        except Exception:
            return _PRODUCTS_CACHE["items"]
    return _PRODUCTS_CACHE["items"]


def _product_summary_line() -> str:
    items = _products()
    if not items:
        return "a range of supplements, teas, skin and oral care"
    cats: Dict[str, int] = {}
    for p in items:
        cats[p.get("categoryName") or p.get("category") or "other"] = cats.get(p.get("categoryName") or p.get("category") or "other", 0) + 1
    return f"{len(items)} products across " + ", ".join(f"{n} ({c})" for n, c in sorted(cats.items()))


def _product_public(p: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a catalog row to what the UI needs."""
    return {
        "code": p.get("code"),
        "name": p.get("name"),
        "spec": p.get("spec"),
        "price": p.get("price"),
        "category": p.get("category"),
        "categoryName": p.get("categoryName"),
        "badge": p.get("badge"),
        "description": p.get("description"),
        "benefits": p.get("benefits") or [],
        "dosage": p.get("dosage"),
        "tags": p.get("tags") or [],
        "image": p.get("image"),
        "gallery": (p.get("gallery") or [p.get("image")])[:4],
    }


_STOPWORDS = set("""a an the and or of for to in on at with my me i we you your is are be it this that what which
who how much cost costs price prices do does have has can could would should please show tell give recommend
something good best help need want looking about from as by if not no yes thanks thank hi hello""".split())


def _product_knowledge_lines() -> List[str]:
    """The store range in a form the agent can quote without inventing anything.

    Names, sizes and prices come straight from the catalog file. Descriptions and
    benefits are trimmed to one clause each so the brief stays readable.
    """
    items = _products()
    if not items:
        return []
    lines = ["Store range, exact names, sizes and prices (never change a price):"]
    for p in sorted(items, key=lambda x: (x.get("categoryName") or "", str(x.get("code") or ""))):
        name = p.get("name") or ""
        spec = p.get("spec") or ""
        price = p.get("price")
        code = p.get("code") or ""
        bit = f"{code} {name}"
        if spec:
            bit += f" ({spec})"
        if price is not None:
            bit += f" R{price:g}" if isinstance(price, (int, float)) else f" R{price}"
        lines.append(bit)
    lines.append(
        "When a guest asks about a product, quote its name, size and price exactly as above. "
        "Describe what it supports using its benefits; never invent a benefit, a price, a "
        "dosage or a cure. Supplements support wellbeing, they do not treat disease."
    )
    return lines


def _product_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Rank products against a free-text query using tags, name, description and benefits."""
    items = _products()
    if not items:
        return []
    raw = (query or "").lower()

    # A product code is an exact identifier: answer it exactly, never by fuzzy match.
    for token in re.findall(r"\b[a-z]\d{1,3}[a-z]?\b", raw):
        for p in items:
            if str(p.get("code", "")).lower() == token:
                return [p]

    tokens = [t for t in re.findall(r"[a-z0-9]+", raw) if len(t) > 2 and t not in _STOPWORDS]
    if not tokens:
        return []
    scored: List[tuple] = []
    for p in items:
        hay_tags = " ".join(p.get("tags") or []).lower()
        hay_name = (p.get("name") or "").lower()
        hay_desc = (p.get("description") or "").lower()
        hay_ben = " ".join(p.get("benefits") or []).lower()
        hay_cat = ((p.get("categoryName") or "") + " " + (p.get("category") or "")).lower()
        score = 0
        for t in tokens:
            if t in hay_tags:
                score += 6
            if t in hay_name:
                score += 5
            if t in hay_ben:
                score += 3
            if t in hay_desc:
                score += 2
            if t in hay_cat:
                score += 2
            if len(t) > 4 and t[:-1] in hay_tags:
                score += 2
        # exact code lookup, e.g. "W01"
        if raw.strip().upper() == (p.get("code") or "").upper():
            score += 50
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], x[1].get("code") or ""))
    return [_product_public(p) for _, p in scored[:limit]]


@app.get("/api/products")
def list_products(category: str = "", q: str = "", limit: int = 100):
    items = _products()
    if q:
        return {"products": _product_search(q, limit=limit)}
    if category:
        items = [p for p in items if (p.get("category") or "") == category]
    return {"products": [_product_public(p) for p in items[:max(1, min(limit, 200))]]}


@app.get("/api/products/{code}")
def get_product(code: str):
    for p in _products():
        if (p.get("code") or "").upper() == code.upper():
            return _product_public(p)
    raise HTTPException(404, "Product not found")



def _clean_reply(text: str) -> str:
    reply = (text or "").strip()
    # Small models leak their reasoning; keep only the answer.
    if "<｜end▁of▁thinking｜>" in reply:
        reply = reply.split("<｜end▁of▁thinking｜>")[-1]
    for marker in ("<|im_end|>", "<|eot_id|>", "</s>"):
        reply = reply.replace(marker, "")
    return reply.strip()


@app.get("/api/assistant/health")
def assistant_health():
    result = {"connected": False, "backends": [], "model": os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)}
    for url, model in _ollama_backends():
        entry = {"url": url, "model": model, "connected": False}
        try:
            req = urllib.request.Request(url + "/api/tags")
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read())
            available = [m.get("name") for m in data.get("models", [])]
            entry["connected"] = True
            entry["has_model"] = model in available
            entry["models"] = available
            result["connected"] = True
        except Exception as exc:
            entry["error"] = str(exc)
        result["backends"].append(entry)
    return result


@app.post("/api/assistant")
def assistant_chat(payload: AssistantRequest, db: Session = Depends(get_db)):
    system_prompt, slots = _assistant_system_prompt(db)
    history = [{"role": m.get("role"), "content": str(m.get("content", ""))[:2000]}
               for m in payload.history[-6:] if m.get("role") in ("user", "assistant")]
    history.append({"role": "user", "content": payload.message[:2000]})
    errors = []
    for base, model in _ollama_backends():
        body = json.dumps({
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, *history],
            "stream": False,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "10m"),
            "options": {"temperature": 0.3, "top_p": 0.9, "num_predict": 220},
        }).encode()
        req = urllib.request.Request(base + "/api/chat", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=int(os.getenv("OLLAMA_TIMEOUT", "90"))) as response:
                data = json.loads(response.read())
            return {"reply": _clean_reply(data.get("message", {}).get("content", "")),
                    "model": data.get("model", model), "backend": base, "slots": slots}
        except Exception as exc:
            errors.append(f"{base}: {exc}")
    raise HTTPException(503, "The assistant is busy right now. Please WhatsApp us on +"
                        + os.getenv("WHATSAPP_NUMBER", "2785771853") + " and we will help you book.")


@app.post("/api/assistant/book", status_code=201)
def assistant_book(payload: dict, db: Session = Depends(get_db)):
    """Create a booking from the assistant's slot picker, reusing the public booking rules."""
    return create_public_booking(payload, db)


# ---------------------------------------------------------------------------
# Admin agent — grounded answers, overdue actions, message drafting
# ---------------------------------------------------------------------------

ADMIN_MODEL = os.getenv("ADMIN_OLLAMA_MODEL", "ihc-admin-1b")


def _money(v) -> str:
    return f"R{int(round(float(v or 0))):,}".replace(",", " ")


def _booking_paid(b: PublicBooking) -> float:
    """What has actually been collected on a booking so far."""
    return round((b.deposit_paid or 0) + ((b.total_fee - b.service.deposit) if b.balance_paid else 0), 2)


def _admin_snapshot(db: Session) -> Dict[str, Any]:
    """Compact JSON facts the admin model is allowed to reason over."""
    today = app_today()
    now = app_now()
    month_start = today.replace(day=1)
    week_start = today - timedelta(days=today.weekday())

    bookings = db.query(PublicBooking).all()
    sales = db.query(WalkInSale).all()
    clients = db.query(Client).all()

    def in_range(rows, start, end):
        return [b for b in rows if b.booking_date and start <= b.booking_date <= end]

    today_rows = in_range(bookings, today, today)
    week_rows = in_range(bookings, week_start, today)
    month_rows = in_range(bookings, month_start, today)

    revenue_today = sum(_booking_paid(b) for b in today_rows) + sum(
        s.amount_zar for s in sales if s.sold_at and s.sold_at.date() == today)
    revenue_week = sum(_booking_paid(b) for b in week_rows) + sum(
        s.amount_zar for s in sales if s.sold_at and s.sold_at.date() >= week_start)
    revenue_month = sum(_booking_paid(b) for b in month_rows) + sum(
        s.amount_zar for s in sales if s.sold_at and s.sold_at.date() >= month_start)

    upcoming = [b for b in bookings
                if b.booking_date >= today
                and datetime.combine(b.booking_date, b.start_time) >= now
                and b.status not in ("cancelled", "completed", "no_show")]
    upcoming.sort(key=lambda b: (b.booking_date, b.start_time))

    pending_deposit = [b for b in bookings if b.status == "pending_deposit"]
    owing = [b for b in bookings
             if (not b.balance_paid) and b.deposit_paid and b.deposit_paid > 0
             and b.status not in ("cancelled", "no_show")]

    # Clients who booked before but not in the last 60 days.
    last_seen: Dict[int, date] = {}
    spend: Dict[int, float] = {}
    visits: Dict[int, int] = {}
    for b in bookings:
        if b.status == "cancelled":
            continue
        if b.client_id not in last_seen or b.booking_date > last_seen[b.client_id]:
            last_seen[b.client_id] = b.booking_date
        spend[b.client_id] = spend.get(b.client_id, 0) + _booking_paid(b)
        if b.status == "completed":
            visits[b.client_id] = visits.get(b.client_id, 0) + 1

    lapsed = []
    for c in clients:
        last = last_seen.get(c.id)
        if last and (today - last).days >= 60:
            lapsed.append({"id": c.id, "name": c.name,
                           "phone": c.phone_whatsapp or c.phone,
                           "days_since": (today - last).days,
                           "last_visit": last.isoformat(),
                           "spend": round(spend.get(c.id, 0), 2),
                           "visits": visits.get(c.id, 0)})
    lapsed.sort(key=lambda x: x["days_since"], reverse=True)

    top_clients = sorted(
        ({"id": c.id, "name": c.name, "phone": c.phone_whatsapp or c.phone,
          "spend": round(spend.get(c.id, 0), 2), "visits": visits.get(c.id, 0)}
         for c in clients if spend.get(c.id)),
        key=lambda x: x["spend"], reverse=True)[:5]

    next_week = today + timedelta(days=7)
    return {
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "money": {
            "revenue_today": round(revenue_today, 2),
            "revenue_this_week": round(revenue_week, 2),
            "revenue_this_month": round(revenue_month, 2),
            "deposits_pending_count": len(pending_deposit),
            "deposits_pending_value": round(sum(b.service.deposit for b in pending_deposit), 2),
            "balances_outstanding_count": len(owing),
            "balances_outstanding_value": round(sum(b.balance_due for b in owing), 2),
        },
        "bookings": {
            "total": len(bookings),
            "today": len(today_rows),
            "upcoming_next_7_days": len([b for b in upcoming if b.booking_date <= next_week]),
            "pending_deposit": len(pending_deposit),
            "awaiting_deposit_list": [
                {"ref": b.booking_ref, "client": b.client.name, "date": b.booking_date.isoformat(),
                 "start": b.start_time.strftime("%H:%M"), "deposit_due": b.service.deposit}
                for b in pending_deposit[:10]],
            "next_up": [
                {"ref": b.booking_ref, "client": b.client.name, "date": b.booking_date.isoformat(),
                 "start": b.start_time.strftime("%H:%M"), "status": b.status,
                 "balance_due": b.balance_due if not b.balance_paid else 0,
                 "phone": b.client.phone_whatsapp or b.client.phone}
                for b in upcoming[:10]],
        },
        "clients": {
            "total": len(clients),
            "lapsed_60_days": len(lapsed),
            "lapsed_list": lapsed[:10],
            "top_by_spend": top_clients,
        },
        "clinic": {
            "office": os.getenv("CLINIC_ADDRESS", "202 Robert Sobukwe Street, Esselen Towers, Sunnyside, Pretoria, 0002"),
            "whatsapp": os.getenv("WHATSAPP_NUMBER", "2785771853"),
            "email": os.getenv("CLINIC_EMAIL", "innerhealthconsult@gmail.com"),
            "hours": _assistant_facts(db)["hours"],
            "services": _assistant_facts(db)["services"],
        },
    }


def _figures(text: str) -> list:
    """Every number and rand amount in a sentence, normalised so R1 350 == R1350."""
    found = re.findall(r"\d[\d\s,.]*", (text or "").replace("\u00a0", " "))
    return [re.sub(r"[\s,]", "", m).rstrip(".") for m in found]


def _same_figures(candidate: str, truth: str) -> bool:
    """True only when the rewrite carries exactly the figures of the source."""
    a, b = _figures(candidate), _figures(truth)
    if len(a) != len(b):
        return False
    return sorted(a) == sorted(b)


def _admin_answer(snapshot: Dict[str, Any], question: str, kind: str) -> str:
    """Deterministic first pass. The model only rephrases this; numbers stay exact."""
    money = snapshot["money"]
    bk = snapshot["bookings"]
    cl = snapshot["clients"]
    q = question.lower()

    # Product questions are answered from the catalog, never with clinic stats
    hits = _product_search(question, limit=3)
    product_words = ("product", "recommend", "supplement", "capsule", "tea", "tablet", "drink",
                     "plaster", "cream", "soap", "price of", "how much is", "cost of", "in store",
                     "stock", "range", "which one", "that one", "first one", "second one", "third one",
                     "blood sugar", "sleep", "energy", "immune", "detox", "joints", "skin",
                     "have you got", "do you sell", "what do you have for", "anything for")
    # A store question is a store question even when the caller sent kind="auto".
    if hits and (kind == "products" or any(w in q for w in product_words)):
        listing = "; ".join(f"{h['name']} ({h['spec']}) R{h['price']}" for h in hits)
        return f"From the store range: {listing}."

    if kind == "money" or any(w in q for w in ("revenue", "money", "takings", "earn", "income", "sales", "rand", "how much did we", "turnover")):
        if not (money['revenue_today'] or money['revenue_this_week'] or money['revenue_this_month']):
            return ("Nothing has been taken yet: no deposits, balances or walk-in sales are recorded "
                    f"for today, this week or this month. {cl['total']} clients and "
                    f"{bk['total']} bookings are on file.")
        return (f"Today {_money(money['revenue_today'])}, this week {_money(money['revenue_this_week'])}, "
                f"this month {_money(money['revenue_this_month'])}. "
                f"Deposits still pending: {money['deposits_pending_count']} worth "
                f"{_money(money['deposits_pending_value'])}. "
                f"Balances outstanding: {money['balances_outstanding_count']} worth "
                f"{_money(money['balances_outstanding_value'])}.")

    if kind == "clients" or any(w in q for w in ("client", "lapsed", "come back", "win back", "dormant", "vip")):
        if not cl['total']:
            return "There are no clients on file yet, so nobody has lapsed."
        top = ", ".join(f"{c['name']} ({_money(c['spend'])})" for c in cl["top_by_spend"][:3]) or "none yet"
        return (f"{cl['total']} clients in total. {cl['lapsed_60_days']} have not been in for 60 days or more. "
                f"Top spenders: {top}.")

    if kind == "deposits" or any(w in q for w in ("deposit", "unpaid", "owing", "outstanding", "chase")):
        rows = bk["awaiting_deposit_list"]
        if not rows:
            return "No bookings are waiting on a deposit right now."
        listing = "; ".join(f"{r['ref']} {r['client']} {r['date']} {r['start']}" for r in rows[:5])
        return (f"{money['deposits_pending_count']} bookings still owe the deposit, "
                f"{_money(money['deposits_pending_value'])} in total: {listing}.")

    if kind == "diary" or any(w in q for w in ("diary", "schedule", "upcoming", "appointment", "tomorrow", "next up")):
        rows = bk["next_up"]
        head = f"{bk['today']} bookings today, {bk['upcoming_next_7_days']} in the next 7 days."
        if not rows:
            return head + " Nothing on the diary is upcoming."
        listing = "; ".join(f"{r['start']} {r['client']} ({r['status']})" for r in rows[:5])
        return head + " Next up: " + listing + "."

    return (f"Patients: {cl['total']}. Bookings: {bk['total']} ({bk['today']} today). "
            f"Revenue today {_money(money['revenue_today'])}, this month {_money(money['revenue_this_month'])}. "
            f"{money['deposits_pending_count']} deposits and {money['balances_outstanding_count']} balances still open.")


# ---------------------------------------------------------------------------
# Agent memory: the admin agent remembers past conversations
# ---------------------------------------------------------------------------

MEMORY_WINDOW = int(os.getenv("AGENT_MEMORY_TURNS", "12"))


def _agent_session(db: Session, session_id: str) -> AgentConversation:
    session_id = (session_id or "default")[:64]
    conv = db.query(AgentConversation).filter_by(session_id=session_id).first()
    if not conv:
        conv = AgentConversation(session_id=session_id, turn_count=0, facts="[]")
        db.add(conv)
        db.commit()
    return conv


def _agent_history(db: Session, session_id: str, limit: int = MEMORY_WINDOW) -> List[Dict[str, str]]:
    rows = (db.query(AgentMessage)
            .filter_by(session_id=session_id)
            .order_by(AgentMessage.id.desc())
            .limit(limit).all())
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def _agent_recent(db: Session, session_id: str, limit: int = 6) -> List[str]:
    """The last few things said in this conversation, oldest first.

    Used so a short follow-up ("and the tea?", "how much?") is read in the light of
    what came before instead of being answered cold.
    """
    try:
        rows = (db.query(AgentMessage)
                .filter_by(session_id=(session_id or "")[:64])
                .order_by(AgentMessage.id.desc())
                .limit(limit).all())
        return [r.content for r in reversed(rows) if r.content]
    except Exception:
        return []


def _agent_remember(db: Session, session_id: str, role: str, content: str, mode: str = "model") -> None:
    content = (content or "").strip()
    if not content:
        return
    db.add(AgentMessage(session_id=session_id[:64], role=role, content=content[:8000], mode=mode))
    conv = _agent_session(db, session_id)
    conv.turn_count = (conv.turn_count or 0) + 1
    conv.last_active = app_now()
    if role == "user" and not conv.title:
        conv.title = content[:120]
    # Roll older turns into the summary so long histories stay cheap
    total = db.query(AgentMessage).filter_by(session_id=session_id[:64]).count()
    if total > 40:
        old = (db.query(AgentMessage).filter_by(session_id=session_id[:64])
               .order_by(AgentMessage.id.asc()).limit(total - 30).all())
        if old:
            lines = [f"{m.role}: {m.content[:160]}" for m in old]
            prior = (conv.summary or "").strip()
            conv.summary = ((prior + "\n") if prior else "") + "\n".join(lines)
            conv.summary = conv.summary[-4000:]
            for m in old:
                db.delete(m)
    db.commit()


def _agent_memory_block(db: Session, session_id: str) -> str:
    """The context the model gets about earlier conversations."""
    conv = db.query(AgentConversation).filter_by(session_id=(session_id or "default")[:64]).first()
    parts = []
    if conv and conv.summary:
        parts.append("EARLIER IN THIS CONVERSATION:\n" + conv.summary[-2500:])
    recent = _agent_history(db, session_id, limit=MEMORY_WINDOW)
    if recent:
        lines = [f"{m['role']}: {m['content'][:400]}" for m in recent]
        parts.append("RECENT TURNS:\n" + "\n".join(lines))
    return "\n\n".join(parts)


@app.get("/api/admin/memory", dependencies=[Depends(require_admin)])
def admin_memory(session_id: str = "default", limit: int = 40):
    """What the agent remembers in this conversation thread."""
    conv = db_session = None
    db = SessionLocal()
    try:
        conv = db.query(AgentConversation).filter_by(session_id=session_id[:64]).first()
        rows = (db.query(AgentMessage).filter_by(session_id=session_id[:64])
                .order_by(AgentMessage.id.desc()).limit(max(1, min(limit, 200))).all())
        return {
            "session_id": session_id,
            "title": conv.title if conv else None,
            "summary": conv.summary if conv else None,
            "turns": conv.turn_count if conv else 0,
            "last_active": conv.last_active.isoformat(timespec="seconds") if conv and conv.last_active else None,
            "messages": [{"role": r.role, "content": r.content, "mode": r.mode,
                          "at": r.created_at.isoformat(timespec="seconds") if r.created_at else None}
                         for r in reversed(rows)],
        }
    finally:
        db.close()


@app.get("/api/admin/memory/threads", dependencies=[Depends(require_admin)])
def admin_memory_threads(limit: int = 20):
    db = SessionLocal()
    try:
        rows = (db.query(AgentConversation).order_by(AgentConversation.last_active.desc())
                .limit(max(1, min(limit, 100))).all())
        return {"threads": [{"session_id": c.session_id, "title": c.title, "turns": c.turn_count,
                             "last_active": c.last_active.isoformat(timespec="seconds") if c.last_active else None}
                            for c in rows]}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Documents: the agent can read what admin uploads and write PDFs to download
# ---------------------------------------------------------------------------

DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(DOCS_DIR, exist_ok=True)

DOC_TEXT_LIMIT = 40000


def _doc_extract(path: str, filename: str) -> tuple:
    """Read a handwritten receipt or note. Returns (text, page_count)."""
    low = (filename or "").lower()
    text, pages = "", None
    try:
        if low.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(path)
            pages = len(reader.pages)
            chunks = []
            for pg in reader.pages:
                try:
                    page_text = pg.extract_text() or ""
                except Exception:
                    page_text = ""
                if page_text.strip():
                    chunks.append(page_text)
            text = "\n".join(chunks)
            # A scanned receipt is a photo inside a PDF: no text layer, so read the page image
            if not text.strip() and pages:
                text = _pdf_pages_as_images(reader)
        elif low.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic")):
            text = _read_handwriting(path)
    except Exception:  # noqa: BLE001
        text = ""
    text = re.sub(r"[ \t]+", " ", (text or "")).strip()
    return text[:DOC_TEXT_LIMIT], pages


def _pdf_pages_as_images(reader, limit: int = 3) -> str:
    """Read a scanned (image-only) PDF by rendering its first pages and reading them."""
    try:
        import fitz  # PyMuPDF, optional
    except Exception:
        return ""
    texts = []
    try:
        import tempfile
        doc = fitz.open(reader.stream.name if hasattr(reader, "stream") else "")
        for i, page in enumerate(doc):
            if i >= limit:
                break
            pix = page.get_pixmap(dpi=200)
            tmp = os.path.join(tempfile.mkdtemp(prefix="ihc-page-"), f"page{i}.png")
            pix.save(tmp)
            texts.append(_read_handwriting(tmp))
            try:
                os.remove(tmp)
            except Exception:
                pass
        doc.close()
    except Exception:
        return ""
    return "\n".join(t for t in texts if t)


def _read_handwriting(image_path: str) -> str:
    """Transcribe a handwritten receipt or note with the local vision model.

    A generic caption is useless here, so the model is told to read the paper
    like a bookkeeper would: every rand amount, date, name and line item.
    """
    import base64
    models = [m.strip() for m in os.getenv("OLLAMA_VISION_MODEL", "llava:latest").split(",") if m.strip()]
    try:
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
    except Exception:
        return ""
    prompt = (
        "This is a photo of a handwritten receipt or handwritten note from a clinic. "
        "Transcribe it line by line exactly as written, including messy handwriting. "
        "Then output these labelled lines when they are present: "
        "DATE: ..., PAYER: ..., AMOUNT: R..., METHOD: cash/card/eft, ITEMS: ..., NOTES: .... "
        "If a value is not written, write 'not written'. Never invent a number, name or date."
    )
    for model in models:
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False, "keep_alive": "10m",
            "options": {"temperature": 0.1, "num_predict": 700},
        }).encode()
        for base, _m in _ollama_backends():
            try:
                req = urllib.request.Request(base + "/api/chat", data=body,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                out = _clean_reply(data.get("message", {}).get("content", ""))
                if len(out) > 10:
                    return out
            except Exception:
                continue
    return ""


@app.post("/api/admin/documents/upload", dependencies=[Depends(require_admin)])
async def upload_document(file: UploadFile = File(...), session_id: str = Form("default"),
                          booking_id: str = Form("")):
    """Upload a PDF, scan image or text file and extract its contents for the agent."""
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "The file is empty")
    if len(raw) > 30 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 30 MB)")
    ext = os.path.splitext(file.filename or "")[1].lower() or ".bin"
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic"):
        raise HTTPException(415, "Upload a photo or scan of a handwritten receipt or note "
                                 "(JPG, PNG, HEIC, TIFF) or a PDF of one.")

    doc_id = uuid.uuid4().hex[:16]
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(file.filename or "upload" + ext))
    dest = os.path.join(DOCS_DIR, f"{doc_id}-{safe_name}")
    with open(dest, "wb") as fh:
        fh.write(raw)

    text, pages = _doc_extract(dest, safe_name)
    db = SessionLocal()
    try:
        doc = AgentDocument(
            doc_id=doc_id, kind="upload", title=file.filename or safe_name, filename=safe_name,
            path=dest, mime=file.content_type, size=len(raw), extracted_text=text,
            page_count=pages, session_id=session_id[:64],
            booking_id=int(booking_id) if str(booking_id).strip().isdigit() else None,
        )
        db.add(doc)
        db.commit()
        emit("document.uploaded", doc_id=doc_id, name=safe_name)
        summary = ""
        if text:
            summary = text[:600] + ("…" if len(text) > 600 else "")
        else:
            summary = "No readable text was found in this file."
        return {
            "doc_id": doc_id, "filename": file.filename, "size": len(raw), "pages": pages,
            "chars": len(text), "summary": summary,
            "can_read": bool(text),
            "download_url": f"/api/admin/documents/{doc_id}/download",
        }
    finally:
        db.close()


@app.get("/api/admin/documents", dependencies=[Depends(require_admin)])
def list_documents(limit: int = 30):
    db = SessionLocal()
    try:
        rows = (db.query(AgentDocument).order_by(AgentDocument.id.desc())
                .limit(max(1, min(limit, 200))).all())
        return {"documents": [{
            "doc_id": d.doc_id, "kind": d.kind, "title": d.title, "filename": d.filename,
            "size": d.size, "pages": d.page_count, "chars": len(d.extracted_text or ""),
            "at": d.created_at.isoformat(timespec="seconds") if d.created_at else None,
            "download_url": f"/api/admin/documents/{d.doc_id}/download",
        } for d in rows]}
    finally:
        db.close()


@app.get("/api/admin/documents/{doc_id}/download")
def download_document(doc_id: str):
    db = SessionLocal()
    try:
        doc = db.query(AgentDocument).filter_by(doc_id=doc_id).first()
        if not doc or not os.path.exists(doc.path):
            raise HTTPException(404, "Document not found")
        return FileResponse(doc.path, filename=doc.filename,
                            media_type=doc.mime or "application/octet-stream")
    finally:
        db.close()


@app.delete("/api/admin/documents/{doc_id}", dependencies=[Depends(require_admin)])
def delete_document(doc_id: str):
    db = SessionLocal()
    try:
        doc = db.query(AgentDocument).filter_by(doc_id=doc_id).first()
        if not doc:
            raise HTTPException(404, "Document not found")
        try:
            os.remove(doc.path)
        except Exception:
            pass
        db.delete(doc)
        db.commit()
        emit("document.deleted", doc_id=doc_id)
        return {"ok": True}
    finally:
        db.close()


# ---- PDF generation -------------------------------------------------------

# Admin operational reports only. Client scan results are never printed here.
def esc_html(text: str) -> str:
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


REPORT_KINDS = {
    "daily": "Daily clinic report",
    "monthly": "Monthly performance report",
    "clients": "Client list and retention",
    "bookings": "Booking register",
    "deposits": "Outstanding deposits and balances",
    "receipts": "Receipts and notes register",
}


def _pdf_report(kind: str, snapshot: Dict[str, Any], title: str = "", db_docs=None) -> tuple:
    """Build a clean, branded A4 PDF and return (path, filename, title)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, KeepTogether)

    money = lambda v: f"R{float(v or 0):,.2f}".replace(",", " ")
    brand = colors.HexColor("#0d805a")
    ink = colors.HexColor("#0b1220")
    soft = colors.HexColor("#f1f5f9")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontName="Helvetica-Bold",
                        fontSize=19, textColor=brand, spaceAfter=2, alignment=0)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#64748b"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                        fontSize=12.5, textColor=ink, spaceBefore=12, spaceAfter=5)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=13.5, textColor=ink)

    heading = title or REPORT_KINDS.get(kind, "Clinic report")
    stamp = app_now()
    filename = f"InnerHealth-{heading.replace(' ', '-')}-{stamp.strftime('%Y%m%d-%H%M')}.pdf"
    path = os.path.join(DOCS_DIR, f"{uuid.uuid4().hex[:16]}-{filename}")

    doc = SimpleDocTemplate(path, pagesize=A4, title=heading, author="Inner Health Consultation Center",
                            leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm)
    story = [
        Paragraph("INNER HEALTH CONSULTATION CENTER", h1),
        Paragraph("202 Robert Sobukwe Street, Esselen Towers, Sunnyside, Pretoria, 0002 &nbsp;·&nbsp; "
                  "WhatsApp 085 771 853 &nbsp;·&nbsp; innerhealthconsult@gmail.com", sub),
        Spacer(1, 10),
        Paragraph(heading, h2),
        Paragraph(f"Generated {stamp.strftime('%A %d %B %Y at %H:%M')}", sub),
        Spacer(1, 8),
    ]

    m = snapshot["money"]
    bk = snapshot["bookings"]
    cl = snapshot["clients"]

    def kv_table(rows, widths=(68 * mm, 40 * mm, 68 * mm, 40 * mm)):
        data = [[Paragraph(f"<b>{a}</b>", body), Paragraph(str(b), body),
                 Paragraph(f"<b>{c}</b>", body), Paragraph(str(d), body)] for a, b, c, d in rows]
        t = Table(data, colWidths=list(widths))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), soft),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    if kind in ("daily", "monthly"):
        story.append(Paragraph("Money at a glance", h2))
        story.append(kv_table([
            ("Revenue today", money(m["revenue_today"]), "Revenue this week", money(m["revenue_this_week"])),
            ("Revenue this month", money(m["revenue_this_month"]), "Deposits pending", f"{m['deposits_pending_count']} · {money(m['deposits_pending_value'])}"),
            ("Balances outstanding", f"{m['balances_outstanding_count']} · {money(m['balances_outstanding_value'])}", "Total bookings", bk["total"]),
        ]))
        story.append(Paragraph("Diary", h2))
        rows = bk.get("next_up") or []
        if rows:
            data = [["Time", "Client", "Status", "Ref"]] + [
                [r.get("start", ""), r.get("client", ""), r.get("status", "").replace("_", " "), r.get("ref", "")]
                for r in rows[:25]]
            t = Table(data, colWidths=[24 * mm, 66 * mm, 40 * mm, 46 * mm], repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), brand),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("No bookings on the diary.", body))

    if kind in ("clients", "monthly"):
        story.append(Paragraph("Clients", h2))
        story.append(kv_table([
            ("Total clients", cl["total"], "Lapsed 60+ days", cl["lapsed_60_days"]),
            ("Top spender", (cl["top_by_spend"][0]["name"] if cl["top_by_spend"] else "—"),
             "Their spend", money(cl["top_by_spend"][0]["spend"]) if cl["top_by_spend"] else "R0"),
        ]))
        if cl["top_by_spend"]:
            data = [["Client", "Spend", "Visits"]] + [
                [c["name"], money(c["spend"]), str(c.get("visits", ""))] for c in cl["top_by_spend"][:20]]
            t = Table(data, colWidths=[86 * mm, 45 * mm, 45 * mm], repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), brand), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ]))
            story.append(t)

    if kind in ("deposits", "monthly"):
        story.append(Paragraph("Money still owed", h2))
        owed = bk.get("awaiting_deposit_list") or []
        if owed:
            data = [["Ref", "Client", "Date", "Time"]] + [
                [r.get("ref", ""), r.get("client", ""), r.get("date", ""), r.get("start", "")] for r in owed[:30]]
            t = Table(data, colWidths=[40 * mm, 66 * mm, 35 * mm, 35 * mm], repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b45309")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("Nothing outstanding.", body))

    if kind == "bookings":
        story.append(Paragraph("All bookings", h2))
        story.append(Paragraph(f"{bk['total']} bookings recorded in total.", body))

    if kind == "receipts":
        story.append(Paragraph("Uploaded receipts and notes", h2))
        docs = (db_docs or [])
        if docs:
            data = [["Uploaded", "File", "Read", "Pages"]] + [
                [(d.created_at.strftime("%d %b %Y %H:%M") if d.created_at else ""),
                 (d.title or d.filename or "")[:52],
                 "yes" if (d.extracted_text or "").strip() else "no",
                 str(d.page_count or "")]
                for d in docs[:40]]
            t = Table(data, colWidths=[34 * mm, 84 * mm, 20 * mm, 20 * mm], repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), brand), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))
            for d in docs[:6]:
                if (d.extracted_text or "").strip():
                    story.append(Paragraph(f"<b>{(d.title or d.filename or '')[:60]}</b>", body))
                    story.append(Paragraph(esc_html(d.extracted_text[:900]).replace("\n", "<br/>"), body))
                    story.append(Spacer(1, 6))
        else:
            story.append(Paragraph("No receipts or notes uploaded yet.", body))

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Generated automatically by the Inner Health admin agent from the live database. "
        "Figures are exact as at the timestamp above.", sub))

    doc.build(story)
    return path, filename, heading


@app.post("/api/admin/documents/report", dependencies=[Depends(require_admin)])
def create_report(payload: dict = Body(default={})):
    """Generate a PDF report and return a download link."""
    kind = str(payload.get("kind") or "daily").lower()
    if kind not in REPORT_KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(REPORT_KINDS)}")
    db = SessionLocal()
    try:
        snapshot = _admin_snapshot(db)
        docs = (db.query(AgentDocument)
                        .order_by(AgentDocument.id.desc()).limit(40).all())
        path, filename, heading = _pdf_report(kind, snapshot, str(payload.get("title") or ""), docs)
        doc_id = uuid.uuid4().hex[:16]
        final = os.path.join(DOCS_DIR, f"{doc_id}-{filename}")
        os.replace(path, final)
        doc = AgentDocument(doc_id=doc_id, kind="report", title=heading, filename=filename,
                            path=final, mime="application/pdf", size=os.path.getsize(final),
                            page_count=None, session_id=str(payload.get("session_id") or "default")[:64])
        db.add(doc)
        db.commit()
        emit("document.generated", doc_id=doc_id, title=heading)
        return {"doc_id": doc_id, "title": heading, "filename": filename,
                "download_url": f"/api/admin/documents/{doc_id}/download",
                "size": os.path.getsize(final)}
    finally:
        db.close()


@app.get("/api/admin/documents/reports", dependencies=[Depends(require_admin)])
def report_kinds():
    return {"kinds": [{"key": k, "title": v} for k, v in REPORT_KINDS.items()]}


@app.delete("/api/admin/memory", dependencies=[Depends(require_admin)])
def admin_memory_clear(session_id: str = "default"):
    db = SessionLocal()
    try:
        db.query(AgentMessage).filter_by(session_id=session_id[:64]).delete()
        db.query(AgentConversation).filter_by(session_id=session_id[:64]).delete()
        db.commit()
        emit("agent.memory_cleared", session_id=session_id)
        return {"ok": True, "session_id": session_id}
    finally:
        db.close()


@app.post("/api/admin/transcribe", dependencies=[Depends(require_admin)])
async def admin_transcribe(audio: UploadFile = File(...)):
    """Transcribe a WhatsApp-style voice note so the admin can talk to the agent.

    Tries the local speech-to-text backends in order (whisper.cpp server, then
    faster-whisper / openai-whisper CLI, then Ollama if a vision/audio model is
    installed). Returns {"text": ...} so the UI can feed it straight to /api/admin/ask.
    """
    raw = await audio.read()
    if not raw:
        raise HTTPException(422, "Empty audio file")
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "Voice note too large (max 25 MB)")

    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    tmp_dir = tempfile.mkdtemp(prefix="ihc-voice-")
    src = os.path.join(tmp_dir, "note" + suffix)
    with open(src, "wb") as fh:
        fh.write(raw)

    def _clean(t: str) -> str:
        t = (t or "").strip()
        for junk in ("[BLANK_AUDIO]", "(silence)", "[silence]", "[Music]", "(music)"):
            t = t.replace(junk, "")
        return re.sub(r"\s+", " ", t).strip()

    # Keep one model loaded between requests: loading it per call cost ~40s.
    global _WHISPER_MODEL
    text = ""
    engine = ""

    try:
        # 1) whisper.cpp / whisper-server on the usual ports
        for port in (8081, 8080, 8001):
            try:
                boundary = "----ihcvoice" + uuid.uuid4().hex
                with open(src, "rb") as fh:
                    payload = fh.read()
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="file"; filename="note{suffix}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/inference",
                    data=body,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                candidate = _clean(data.get("text", ""))
                if candidate:
                    text, engine = candidate, f"whisper-server:{port}"
                    break
            except Exception:
                continue

        # 2) faster-whisper or openai-whisper installed locally
        if not text:
            for cmd in (
                ["whisper", src, "--model", "base", "--output_format", "txt", "--output_dir", tmp_dir],
            ):
                try:
                    proc = subprocess.run(cmd, capture_output=True, timeout=180)
                    if proc.returncode == 0:
                        out = os.path.join(tmp_dir, "note.txt")
                        if os.path.exists(out):
                            candidate = _clean(open(out, encoding="utf-8", errors="ignore").read())
                            if candidate:
                                text, engine = candidate, "whisper-cli"
                                break
                except Exception:
                    continue

        # 3) faster_whisper python package
        if not text:
            try:
                if _WHISPER_MODEL is None:
                    from faster_whisper import WhisperModel  # type: ignore
                    _WHISPER_MODEL = WhisperModel(
                        os.getenv("WHISPER_MODEL", "base"),
                        device="cpu", compute_type="int8",
                        cpu_threads=max(2, os.cpu_count() or 2),
                    )
                segments, _info = _WHISPER_MODEL.transcribe(
                    src, beam_size=1, vad_filter=True, language="en",
                    condition_on_previous_text=False,
                )
                candidate = _clean(" ".join(seg.text for seg in segments))
                if candidate:
                    text, engine = candidate, "faster-whisper"
            except Exception:
                pass

        # 4) Ollama audio model, if one has been pulled
        if not text:
            audio_model = os.getenv("OLLAMA_AUDIO_MODEL", "")
            if audio_model:
                import base64
                b64 = base64.b64encode(raw).decode()
                body = json.dumps({
                    "model": audio_model,
                    "messages": [{"role": "user", "content": "Transcribe this audio exactly. Output only the words spoken.", "images": [b64]}],
                    "stream": False, "keep_alive": "5m",
                }).encode()
                for base, _m in _ollama_backends():
                    try:
                        req = urllib.request.Request(base + "/api/chat", data=body, headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(req, timeout=120) as resp:
                            data = json.loads(resp.read())
                        candidate = _clean(_clean_reply(data.get("message", {}).get("content", "")))
                        if candidate:
                            text, engine = candidate, f"ollama:{audio_model}"
                            break
                    except Exception:
                        continue
    finally:
        try:
            os.remove(src)
            os.rmdir(tmp_dir)
        except Exception:
            pass

    if not text:
        return {
            "text": "",
            "engine": "none",
            "detail": "No speech-to-text engine is installed on this computer. Type the question instead, or install whisper (pip install faster-whisper) or run whisper-server.",
        }
    return {"text": text, "engine": engine, "chars": len(text)}


@app.get("/api/admin/transcribe/health")
def transcribe_health():
    """Report which speech-to-text engines are available right now."""
    found = {"whisper_server": None, "whisper_cli": False, "faster_whisper": False, "ollama_audio": os.getenv("OLLAMA_AUDIO_MODEL", "") or None}
    for port in (8081, 8080, 8001):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                if resp.status < 500:
                    found["whisper_server"] = port
                    break
        except Exception:
            continue
    found["whisper_cli"] = bool(shutil.which("whisper"))
    try:
        import faster_whisper  # type: ignore  # noqa: F401
        found["faster_whisper"] = True
    except Exception:
        pass
    ready = bool(found["whisper_server"] or found["whisper_cli"] or found["faster_whisper"] or found["ollama_audio"])
    return {"ready": ready, "engines": found}


@app.post("/api/admin/ask", dependencies=[Depends(require_admin)])
def admin_ask(payload: dict, db: Session = Depends(get_db)):
    """Ask the admin agent about anything in the hub. Always answers, even with no model."""
    question = str(payload.get("question", "")).strip()[:600]
    kind = str(payload.get("kind", "auto"))[:20]
    session_id = str(payload.get("session_id") or "default")[:64]
    if not question and kind == "auto":
        raise HTTPException(422, "Ask a question first")

    snapshot = _admin_snapshot(db)
    memory = _agent_memory_block(db, session_id)

    # If admin has uploaded a document in this thread, answer from its contents
    if payload.get("use_documents", True):
        doc = (db.query(AgentDocument)
               .filter(AgentDocument.session_id == session_id, AgentDocument.extracted_text.isnot(None))
               .order_by(AgentDocument.id.desc()).first())
        if doc and (doc.extracted_text or "").strip():
            snippet = doc.extracted_text[:6000]
            answer = (f"From the document you sent ({doc.title or doc.filename}):\n\n{snippet}")
            return {"answer": answer, "mode": "document", "facts": snapshot, "products": [],
                    "session_id": session_id,
                    "document": {"doc_id": doc.doc_id, "title": doc.title,
                                 "download_url": f"/api/admin/documents/{doc.doc_id}/download"}}
    answer = _admin_answer(snapshot, question, kind)

    # Conversation: if the guest is following on ("and the tea?", "how much?"), the
    # previous turns tell us what they mean. Short follow-ups inherit the topic.
    try:
        recent = _agent_recent(db, session_id, limit=6)
    except Exception:
        recent = []
    follow_up = bool(question) and len(question.strip().split()) <= 6 and not _product_search(question, limit=1)
    if follow_up and recent:
        topic = " ".join(r for r in recent if r and len(r) > 3)[-300:]
        carried = _product_search(topic, limit=3)
        if carried and "From the store range" not in answer:
            listing = "; ".join(f"{p['name']} ({p['spec']}) R{p['price']}" for p in carried)
            answer = f"Following on from what we just discussed: {listing}."
    product_words = ("product", "recommend", "supplement", "capsule", "tea", "tablet", "drink",
                     "plaster", "cream", "soap", "in store", "stock", "range", "which one",
                     "that one", "first one", "second one", "third one", "how much is the",
                     "how much is", "price of", "cost of", "have you got", "do you sell")
    is_product_q = bool(question) and any(w in question.lower() for w in product_words)
    product_hits = _product_search(question, limit=3) if is_product_q else []
    if product_hits and "From the store range" not in answer:
        listing = "; ".join(f"{p['name']} ({p['spec']}) R{p['price']}" for p in product_hits)
        if is_product_q:
            # A store question must be answered with the store, not with clinic takings.
            answer = f"From the store range: {listing}."
        else:
            answer = answer.rstrip() + "\n\nIn store: " + listing + "."
    mode = "rules"

    # Rephrasing is optional polish. It is skipped unless a model is explicitly
    # nominated for it, because the drafts are already correct and a small model
    # only risks corrupting them.
    polish_model = os.getenv("ADMIN_POLISH_MODEL", "").strip()
    try:
        if not polish_model:
            raise RuntimeError("rephrasing disabled")
        system = (
            "You are the internal admin assistant for Inner Health Consultation Center, Pretoria. "
            "You answer the owner only. You are given FACTS and a DRAFT answer computed from the live database. "
            "Keep every number and name exactly as in the draft. Rewrite the draft into at most three short, "
            "clear sentences. Never invent a client, amount, phone number or date. If the draft does not answer "
            "the question, say what data is missing instead of guessing. No markdown."
        )
        user = ((memory + "\n\n" if memory else "")
                + "FACTS:\n" + json.dumps(snapshot, ensure_ascii=False)[:5000]
                + "\n\nDRAFT ANSWER:\n" + answer
                + "\n\nQUESTION: " + (question or "Give the daily summary"))
        body = json.dumps({
            "model": polish_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "keep_alive": "10m",
            "options": {"temperature": 0.1, "num_predict": 180},
        }).encode()
        for base, _model in _ollama_backends():
            try:
                req = urllib.request.Request(base + "/api/chat", data=body,
                                            headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=25) as response:
                    data = json.loads(response.read())
                polished = _clean_reply(data.get("message", {}).get("content", ""))
                low = polished.lower()
                # A 1B model sometimes refuses or asks for data; the draft is already correct.
                refusal = any(k in low for k in (
                    "can't answer", "cannot answer", "what data is missing", "data missing",
                    "missing from the facts", "i don't know", "i do not know", "unable to answer",
                    "no data", "not enough information", "does not contain", "do not contain",
                    "doesn't contain", "don't contain", "not provided", "isn't provided",
                    "cannot provide", "can't provide", "medical advice",
                    "anything else i can help", "not able to provide",
                    "consult a doctor", "speak to a doctor", "based on the facts"))
                # Every local model tested (ihc-admin-1b, ihc-llama32-3b, llama3.2,
                # qwen3:4b) either refused the question or invented figures, so the
                # rephrasing is only accepted when it reproduces the draft's figures
                # exactly. Otherwise the database's own wording stands.
                if len(polished) > 20 and not refusal and _same_figures(polished, answer):
                    answer = polished
                    mode = "model"
                break
            except Exception:
                continue
    except Exception:
        pass

    products = _product_search(question, limit=3) if question else []

    # Remember the turn so the next question has context
    try:
        _agent_remember(db, session_id, "user", question or kind, mode)
        _agent_remember(db, session_id, "assistant", answer, mode)
    except Exception:
        db.rollback()

    return {"answer": answer, "mode": mode, "facts": snapshot, "products": products,
            "session_id": session_id}


def _whatsapp_link(phone: Optional[str], message: str) -> str:
    digits = re.sub(r"[^0-9]", "", phone or "")
    if digits.startswith("0") and len(digits) >= 10:
        digits = "27" + digits[1:]
    return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"


def _wa_draft_rules(ctx: Dict[str, Any]) -> str:
    """A solid message written from the facts, used when no model is available."""
    first = (ctx.get("name") or "there").split()[0]
    kind = ctx.get("kind") or "reminder"
    clinic = "Inner Health Consultation Center"
    when = ctx.get("when") or ""
    ref = ctx.get("ref") or ""
    amount = ctx.get("amount")
    if kind == "deposit":
        return (f"Hi {first}, this is {clinic}. Your full-body scan on {when} is not confirmed yet. "
                f"The R{int(amount or 150)} deposit secures the time. Reference {ref}. "
                f"Bank: FNB, Ntombikayise N Mkhaliphi, 62804835835, branch 250655. Reply here if you need help.")
    if kind == "balance":
        return (f"Hi {first}, a reminder of your scan on {when}. The balance of R{int(amount or 300)} "
                f"is due at reception. Reference {ref}. {clinic}, 202 Robert Sobukwe Street, Esselen Towers, Sunnyside.")
    if kind == "winback":
        return (f"Hi {first}, it has been a while since your last scan with {clinic}. "
                f"If you would like to come in again, reply here and we will find you a time. "
                f"A scan is R450 with a R150 deposit.")
    if kind == "thanks":
        return (f"Hi {first}, thank you for coming in today for your scan. If anything was not clear, "
                f"reply here and we will help. {clinic}.")
    return (f"Hi {first}, looking forward to seeing you {when} for your full-body scan at "
            f"202 Robert Sobukwe Street, Esselen Towers, Sunnyside. Reference {ref}. {clinic}.")


@app.post("/api/admin/whatsapp/draft", dependencies=[Depends(require_admin)])
def admin_whatsapp_draft(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Draft a WhatsApp message for one client. The agent writes it; staff send it.

    Nothing is sent from here. The reply carries a wa.me link the staff member taps,
    so the message leaves from the clinic's own WhatsApp number and stays in its history.
    """
    name = str(payload.get("name") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    kind = str(payload.get("kind") or "reminder").strip().lower()
    ref = payload.get("ref")
    when = str(payload.get("when") or "")
    amount = payload.get("amount")
    extra = str(payload.get("note") or "").strip()

    # If a booking reference was given, take the facts from the database, not the client
    if ref:
        b = db.query(PublicBooking).filter(PublicBooking.booking_ref == ref).first()
        if b:
            name = b.client.name
            phone = b.client.phone_whatsapp or b.client.phone or phone
            when = f"{b.booking_date:%A %d %B} at {b.start_time:%H:%M}"
            amount = b.balance_due if not b.balance_paid else b.service.deposit
            if not kind or kind == "auto":
                kind = "deposit" if b.status == "pending_deposit" else (
                    "balance" if not b.balance_paid else "reminder")

    ctx = {"name": name, "kind": kind, "when": when, "ref": ref, "amount": amount}
    fallback = _wa_draft_rules(ctx)

    drafted, mode = fallback, "rules"
    question = (f"Write one WhatsApp message to {name.split()[0] if name else 'the client'} about: "
                f"{kind}. Facts you may use: appointment {when or 'not given'}; reference {ref or 'none'}; "
                f"amount R{amount if amount not in (None, '') else 'not given'}; "
                f"clinic Inner Health Consultation Center at 202 Robert Sobukwe Street, Esselen Towers, "
                f"Sunnyside, Pretoria; WhatsApp 2785771853. "
                f"Rules: under 60 words, warm and plain, no emoji unless the note asks, "
                f"never invent a date, amount or reference, no medical advice. "
                + (f"Staff note to include: {extra}. " if extra else "")
                + "Reply with the message text only, no preamble and no quotation marks.")
    try:
        for base, model in _ollama_backends():
            body = json.dumps({"model": model,
                               "messages": [{"role": "system",
                                             "content": "You write short, clear WhatsApp messages for a health clinic. "
                                                        "You never invent facts."},
                                            {"role": "user", "content": question}],
                               "stream": False, "keep_alive": "10m",
                               "options": {"temperature": 0.3, "num_predict": 160}}).encode()
            req = urllib.request.Request(base + "/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                out = _clean_reply(json.loads(resp.read()).get("message", {}).get("content", ""))
            if out and 20 <= len(out) <= 700 and not re.search(r"(?i)(can't answer|data missing|as an ai)", out):
                drafted, mode = out.strip('"').strip(), "model"
                break
    except Exception:
        pass

    return {"message": drafted, "mode": mode, "kind": kind, "name": name, "phone": phone,
            "wa": _whatsapp_link(phone, drafted) if phone else ""}


@app.get("/api/admin/whatsapp/notify", dependencies=[Depends(require_admin)])
def admin_whatsapp_notify_get():
    """Where the clinic owner's own notifications go, and how to set it up."""
    number = os.getenv("OWNER_WHATSAPP", "").strip()
    return {"number": number, "configured": bool(number),
            "hint": "Set OWNER_WHATSAPP in .env to the owner's number in international format, "
                    "for example 27821234567, then restart the service."}


@app.post("/api/admin/whatsapp/notify", dependencies=[Depends(require_admin)])
def admin_whatsapp_notify(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Build the owner's own notification: a new booking, a deposit paid, a balance collected.

    Returns a wa.me link addressed to the owner's number so the notification is one tap away.
    """
    event = str(payload.get("event") or "new_booking")
    ref = payload.get("ref")
    owner = os.getenv("OWNER_WHATSAPP", "").strip()
    clinic = "Inner Health Consultation Center"
    lines = []
    if ref:
        b = db.query(PublicBooking).filter(PublicBooking.booking_ref == ref).first()
        if b:
            who = b.client.name
            phone = b.client.phone_whatsapp or b.client.phone or "no number"
            if event == "deposit_paid":
                lines = [f"Deposit paid: R{int(b.deposit_paid)} from {who}.",
                         f"{b.service.name} on {b.booking_date:%a %d %b} at {b.start_time:%H:%M}.",
                         f"Ref {b.booking_ref}. Balance still due R{int(b.balance_due)}."]
            elif event == "balance_paid":
                lines = [f"Paid in full: {who}, R{int(b.total_fee)}.",
                         f"{b.service.name} on {b.booking_date:%a %d %b} at {b.start_time:%H:%M}.",
                         f"Ref {b.booking_ref}. Nothing outstanding."]
            elif event == "cancelled":
                lines = [f"Cancelled: {who}, {b.booking_date:%a %d %b} at {b.start_time:%H:%M}.",
                         f"Ref {b.booking_ref}. The slot is free again.", f"Client: {phone}."]
            else:
                lines = [f"New booking: {who}.",
                         f"{b.service.name} on {b.booking_date:%a %d %b} at {b.start_time:%H:%M}.",
                         f"Ref {b.booking_ref}. Deposit R{int(b.service.deposit)} "
                         f"{'paid' if b.deposit_paid else 'still outstanding'}.",
                         f"Client: {phone}."]
    if not lines:
        lines = [f"{clinic}: {event.replace('_', ' ')}."]
    text = "\n".join(lines)
    return {"message": text, "number": owner, "configured": bool(owner),
            "wa": _whatsapp_link(owner, text) if owner else ""}


# ---------------------------------------------------------------- installable app
@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest():
    """Web app manifest so the admin dashboard installs as an app on her phone."""
    return JSONResponse({
        "name": "Inner Health Admin",
        "short_name": "IH Admin",
        "description": "Inner Health Consultation Center - bookings, diary, clients and the AI agent.",
        "start_url": "/admin/bookings",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#07131b",
        "theme_color": "#101a2d",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Diary", "url": "/admin/bookings#diary"},
            {"name": "Ask the agent", "url": "/admin/bookings#agent"},
        ],
    })


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def asset_links():
    """Digital Asset Links. Required before an Android package can open the dashboard
    full screen instead of inside a browser tab. The fingerprint is set once the
    package is built, in ANDROID_SHA256_FINGERPRINT."""
    fp = os.getenv("ANDROID_SHA256_FINGERPRINT", "").strip()
    pkg = os.getenv("ANDROID_PACKAGE_NAME", "za.co.innerhealth.admin").strip()
    if not fp:
        return JSONResponse([], media_type="application/json")
    return JSONResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {"namespace": "android_app", "package_name": pkg,
                   "sha256_cert_fingerprints": [fp]},
    }], media_type="application/json")


@app.api_route("/wake", methods=["GET", "HEAD"], include_in_schema=False)
def wake():
    """Tiny, unauthenticated endpoint the phone app hits first to start a sleeping
    instance while the user is still walking to the app. Answers instantly."""
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


CLINIC_EMAIL = os.getenv("CLINIC_EMAIL", "innerhealthconsult@gmail.com")
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _gmail_access_token() -> Optional[str]:
    """Access token for the clinic's Gmail. Prefers the token saved when the owner tapped
    Connect, then falls back to an environment refresh token or a service account."""
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    refresh = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    if not refresh:
        _db = SessionLocal()
        try:
            refresh = _setting_get(_db, "google_refresh_token").strip()
        finally:
            _db.close()
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    try:
        if refresh and client_id and client_secret:
            data = urllib.parse.urlencode({
                "client_id": client_id, "client_secret": client_secret,
                "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
            req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data,
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read()).get("access_token")
        if creds_path and os.path.exists(creds_path):
            from google.oauth2 import service_account  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore
            creds = service_account.Credentials.from_service_account_file(
                creds_path, scopes=["https://www.googleapis.com/auth/gmail.send"],
                subject=os.getenv("GMAIL_SEND_AS", CLINIC_EMAIL))
            creds.refresh(Request())
            return creds.token
    except Exception as exc:  # noqa: BLE001
        print(f"Gmail token failed: {exc}")
    return None


def _send_email(to_addr: str, subject: str, body: str, html: bool = False) -> Dict[str, Any]:
    """Send one email as the clinic. Tries Gmail, then SMTP, and reports which worked."""
    if not to_addr:
        return {"sent": False, "via": None, "reason": "no email address"}
    from email.message import EmailMessage
    import base64

    mail = EmailMessage()
    mail["Subject"] = subject
    mail["From"] = f"Inner Health Consultation Center <{CLINIC_EMAIL}>"
    mail["To"] = to_addr
    if html:
        mail.set_content("This message needs an HTML capable reader.")
        mail.add_alternative(body, subtype="html")
    else:
        mail.set_content(body)

    token = _gmail_access_token()
    if token:
        try:
            raw = base64.urlsafe_b64encode(mail.as_bytes()).decode()
            req = urllib.request.Request(GMAIL_SEND_URL, data=json.dumps({"raw": raw}).encode(),
                                         headers={"Authorization": f"Bearer {token}",
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status in (200, 202):
                    return {"sent": True, "via": "gmail"}
        except Exception as exc:  # noqa: BLE001
            print(f"Gmail send failed, trying SMTP: {exc}")

    if os.getenv("SMTP_HOST"):
        try:
            import smtplib
            port = int(os.getenv("SMTP_PORT", "587"))
            host = os.getenv("SMTP_HOST")
            with smtplib.SMTP(host, port, timeout=12) as smtp:
                smtp.starttls()
                if os.getenv("SMTP_USER"):
                    smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
                smtp.send_message(mail)
            return {"sent": True, "via": "smtp"}
        except Exception as exc:  # noqa: BLE001
            print(f"SMTP send failed: {exc}")
            return {"sent": False, "via": None, "reason": str(exc)}

    return {"sent": False, "via": None,
            "reason": "no mail transport configured (set GOOGLE_REFRESH_TOKEN or SMTP_HOST)"}


@app.get("/api/admin/email/status", dependencies=[Depends(require_admin)])
def admin_email_status():
    """Whether this server can actually send mail, and by which route."""
    token = _gmail_access_token()
    db = SessionLocal()
    try:
        stored = bool(_setting_get(db, "google_refresh_token").strip())
    finally:
        db.close()
    return {"clinic_email": CLINIC_EMAIL,
            "gmail": bool(token),
            "gmail_connected": stored,
            "smtp": bool(os.getenv("SMTP_HOST")),
            "ready": bool(token) or bool(os.getenv("SMTP_HOST")),
            "connect_url": "/api/google/start"}


@app.post("/api/admin/email/test", dependencies=[Depends(require_admin)])
def admin_email_test(payload: Dict[str, Any]):
    """Send a test message so the owner can see it arrive."""
    to_addr = str(payload.get("to") or CLINIC_EMAIL)
    result = _send_email(to_addr, "Inner Health - email test",
                         "This is a test from the Inner Health admin dashboard. "
                         "If you are reading this, booking confirmations and reminders will send.")
    return {"to": to_addr, **result}


# ------------------------------------------------------- Google connect (one tap on a phone)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def _google_redirect_uri() -> str:
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    return base + "/api/google/callback"


@app.get("/api/google/start")
def google_start():
    """Where the owner lands after Google. Opens the consent screen straight away."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        return HTMLResponse(
            "<h2>Not ready yet</h2><p>The clinic's Google client ID has not been added to the "
            "server yet. Ask whoever is building the site to set GOOGLE_CLIENT_ID, then open "
            "this link again.</p>", status_code=503)
    params = {
        "client_id": client_id,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": GMAIL_SEND_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "login_hint": CLINIC_EMAIL,
    }
    return RedirectResponse(GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params), status_code=302)


@app.get("/api/google/qr.png")
def google_qr():
    """A QR code of the connect link, so the owner can scan it instead of typing a URL."""
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    target = base + "/api/google/start"
    try:
        import io
        import qrcode
        from qrcode.image.pil import PilImage  # noqa: F401
        qr = qrcode.QRCode(box_size=10, border=3,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(target)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0b2a22", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png",
                        headers={"Cache-Control": "no-store"})
    except Exception as exc:  # noqa: BLE001
        return Response(content=f"could not build QR: {exc}".encode(), status_code=500,
                        media_type="text/plain")


@app.get("/connect", include_in_schema=False)
def connect_page():
    """A single page showing a big QR code and a tap-through button."""
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    link = base + "/api/google/start"
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect Inner Health email</title></head>
<body style="font-family:system-ui,sans-serif;margin:0;background:#f6f9fb;text-align:center">
<div style="max-width:32rem;margin:6vh auto;background:#fff;border:1px solid #e2e8f0;
border-radius:20px;padding:1.6rem;box-shadow:0 12px 30px -18px rgba(11,18,32,.3)">
<h1 style="font-size:1.15rem;margin:0 0 .4rem;color:#0b2a22">Connect the clinic's email</h1>
<p style="color:#475569;font-size:.9rem;margin:0 0 1.2rem;line-height:1.5">
Point the phone camera at this code, then tap the link it shows.</p>
<img src="/api/google/qr.png" alt="QR code" style="width:min(70vw,17rem);height:auto;display:block;margin:0 auto 1.2rem">
<a href="{esc_html(link)}" style="display:inline-block;background:#0d805a;color:#fff;text-decoration:none;
padding:.75rem 1.4rem;border-radius:12px;font-weight:600;font-size:.92rem">Or tap here to connect</a>
<p style="color:#94a3b8;font-size:.78rem;margin:1.2rem 0 0;line-height:1.5">
Sign in as innerhealthconsult@gmail.com and tap Allow. Only sending email is granted.</p>
</div></body></html>""")


@app.get("/api/google/callback", include_in_schema=False)
def google_callback(code: str = "", error: str = "", state: str = ""):
    """Google sends the owner back here with a one-time code. It is swapped for a refresh
    token and stored, so nobody ever has to copy a code by hand."""
    def page(title: str, body: str, ok: bool) -> HTMLResponse:
        colour = "#0d805a" if ok else "#b91c1c"
        return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head>
<body style="font-family:system-ui,sans-serif;margin:0;background:#f6f9fb">
<div style="max-width:34rem;margin:12vh auto;background:#fff;border:1px solid #e2e8f0;
border-radius:16px;padding:1.6rem;box-shadow:0 12px 30px -18px rgba(11,18,32,.3)">
<h1 style="font-size:1.15rem;margin:0 0 .6rem;color:{colour}">{title}</h1>
<div style="color:#334155;font-size:.92rem;line-height:1.55">{body}</div></div></body></html>""")

    if error:
        return page("Permission was not granted",
                    "Google reported: <b>" + esc_html(error) + "</b>. You can close this page and "
                    "open the link again if you would like to try.", False)
    if not code:
        return page("No code came back",
                    "Google did not send an authorisation code. Open the link again from the start.", False)

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return page("Server is not configured",
                    "The client ID or secret is missing on the server, so the code cannot be "
                    "exchanged. Send this page's URL to whoever is building the site.", False)

    data = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": _google_redirect_uri(), "grant_type": "authorization_code"}).encode()
    try:
        req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        return page("Google refused the exchange",
                    "This usually means the link was already used, or it sat open too long. "
                    "Open the link again and it will work. Details: <code>" + esc_html(str(exc)[:200]) + "</code>", False)

    refresh = payload.get("refresh_token")
    if not refresh:
        return page("No lasting token came back",
                    "Google returned an access token but no refresh token. Open the link again - "
                    "it always asks for consent fresh, which is what makes this work.", False)

    # Store it in the app's own settings table so a redeploy cannot lose it
    db = SessionLocal()
    try:
        _setting_set(db, "google_refresh_token", refresh)
        _setting_set(db, "google_connected_email", CLINIC_EMAIL)
        db.commit()
    finally:
        db.close()
    emit("google.connected")
    return page("Email is connected",
                "Inner Health can now send email as <b>" + esc_html(CLINIC_EMAIL) + "</b>. "
                "Booking confirmations and reminders will send by themselves from now on. "
                "You can close this page.", True)


def _setting_set(db: Session, key: str, value: str) -> None:
    """Tiny key/value store for things that must survive a redeploy."""
    try:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
    except Exception as exc:  # noqa: BLE001
        print(f"setting save failed: {exc}")


def _setting_get(db: Session, key: str) -> str:
    try:
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else ""
    except Exception:  # noqa: BLE001
        return ""


@app.get("/api/admin/follow-ups", dependencies=[Depends(require_admin)])
def admin_follow_ups(db: Session = Depends(get_db)):
    """Everyone who needs a nudge today, with a ready WhatsApp message each."""
    today = app_today()
    now = app_now()
    clinic = "Inner Health Consultation Center"
    origin = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    buckets = {"deposit": [], "balance": [], "reminder": [], "winback": []}
    snapshot = _admin_snapshot(db)

    for b in db.query(PublicBooking).filter(PublicBooking.status == "pending_deposit").all():
        msg = (f"Hi {b.client.name.split()[0]}, this is {clinic}. Your full-body scan on "
               f"{b.booking_date:%A %d %B} at {b.start_time:%H:%M} is not confirmed yet. "
               f"The R{int(b.service.deposit)} deposit secures the time. Reference {b.booking_ref}. "
               f"Bank: FNB, Ntombikayise N Mkhaliphi, 62804835835, branch 250655.")
        buckets["deposit"].append({"ref": b.booking_ref, "name": b.client.name,
                                   "phone": b.client.phone_whatsapp or b.client.phone,
                                   "when": f"{b.booking_date:%d %b} {b.start_time:%H:%M}",
                                   "amount": b.service.deposit, "message": msg,
                                   "wa": _whatsapp_link(b.client.phone_whatsapp or b.client.phone, msg)})

    for b in db.query(PublicBooking).filter(PublicBooking.balance_paid == False).all():  # noqa: E712
        if b.status in ("cancelled", "no_show") or not b.deposit_paid:
            continue
        msg = (f"Hi {b.client.name.split()[0]}, a reminder of your scan on "
               f"{b.booking_date:%A %d %B} at {b.start_time:%H:%M}. The balance of "
               f"R{int(b.balance_due)} is due at reception. Reference {b.booking_ref}. {clinic}.")
        buckets["balance"].append({"ref": b.booking_ref, "name": b.client.name,
                                   "phone": b.client.phone_whatsapp or b.client.phone,
                                   "when": f"{b.booking_date:%d %b} {b.start_time:%H:%M}",
                                   "amount": b.balance_due, "message": msg,
                                   "wa": _whatsapp_link(b.client.phone_whatsapp or b.client.phone, msg)})

    for b in db.query(PublicBooking).all():
        when = datetime.combine(b.booking_date, b.start_time)
        if b.status not in ("confirmed", "arriving_soon"):
            continue
        hours = (when - now).total_seconds() / 3600
        if not (0 < hours <= 30):
            continue
        msg = (f"Hi {b.client.name.split()[0]}, looking forward to seeing you "
               f"{b.booking_date:%A} at {b.start_time:%H:%M} for your full-body scan at "
               f"202 Robert Sobukwe Street, Esselen Towers, Sunnyside. Reference {b.booking_ref}. {clinic}.")
        buckets["reminder"].append({"ref": b.booking_ref, "name": b.client.name,
                                    "phone": b.client.phone_whatsapp or b.client.phone,
                                    "when": f"{b.booking_date:%d %b} {b.start_time:%H:%M}",
                                    "amount": b.balance_due if not b.balance_paid else 0,
                                    "message": msg,
                                    "wa": _whatsapp_link(b.client.phone_whatsapp or b.client.phone, msg)})

    for row in snapshot["clients"]["lapsed_list"]:
        msg = (f"Hi {row['name'].split()[0]}, it is a while since your last scan with {clinic}. "
               f"If you would like to come in again, reply here and we will find you a time. "
               f"A scan is R450 with a R150 deposit.")
        buckets["winback"].append({"ref": None, "name": row["name"], "phone": row["phone"],
                                   "when": f"{row['days_since']} days ago",
                                   "amount": 0, "message": msg,
                                   "wa": _whatsapp_link(row["phone"], msg)})

    return {"generated": today.isoformat(), "counts": {k: len(v) for k, v in buckets.items()}, "buckets": buckets}


@app.get("/api/admin/report", dependencies=[Depends(require_admin)])
def admin_report(db: Session = Depends(get_db)):
    """Month-to-date performance plus the 6-month trend, for printing or pasting."""
    today = app_today()
    snapshot = _admin_snapshot(db)
    bookings = db.query(PublicBooking).all()
    sales = db.query(WalkInSale).all()

    trend = []
    for back in range(5, -1, -1):
        month = (today.replace(day=1) - timedelta(days=back * 30)).replace(day=1)
        end = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        rows = [b for b in bookings if b.booking_date and month <= b.booking_date < end]
        rev = sum(_booking_paid(b) for b in rows) + sum(
            s.amount_zar for s in sales if s.sold_at and month <= s.sold_at.date() < end)
        trend.append({"month": month.strftime("%b %Y"), "bookings": len(rows), "revenue": round(rev, 2)})

    by_status: Dict[str, int] = {}
    for b in bookings:
        by_status[b.status] = by_status.get(b.status, 0) + 1

    return {
        "generated_at": app_now().isoformat(timespec="minutes"),
        "summary": snapshot["money"],
        "bookings": snapshot["bookings"],
        "clients": {k: snapshot["clients"][k] for k in ("total", "lapsed_60_days", "top_by_spend")},
        "by_status": by_status,
        "trend": trend,
    }

# ---------------------------------------------------------------------------
# Public Booking APIs
# ---------------------------------------------------------------------------

@app.get("/api/public/config")
def public_config():
    return {
        "facebook": os.getenv("FACEBOOK_URL", "https://www.facebook.com/share/1Cfx8cayqM/"),
        "instagram": os.getenv("INSTAGRAM_URL", ""),
        "tiktok": os.getenv("TIKTOK_URL", ""),
        "whatsapp": os.getenv("WHATSAPP_NUMBER", "2785771853"),
        "email": os.getenv("CLINIC_EMAIL", "innerhealthconsult@gmail.com"),
        "business_name": "Inner Health Consultation Center",
        "address": os.getenv("CLINIC_ADDRESS", "202 Robert Sobukwe Street, Esselen Towers, Sunnyside, Pretoria, 0002"),
    }

@app.get("/api/public/services")
def public_services(db: Session = Depends(get_db)):
    return [
        {"id": s.id, "name": s.name, "description": s.description,
         "duration_minutes": s.duration_minutes, "price": s.price, "deposit": s.deposit}
        for s in db.query(BookingService).filter_by(is_active=True).all()
    ]

@app.get("/api/public/calendar")
def public_calendar(month: str, service_id: int, db: Session = Depends(get_db)):
    service = db.query(BookingService).filter_by(id=service_id, is_active=True).first()
    if not service:
        raise HTTPException(404, "service not found")
    try:
        yr, mo = map(int, month.split("-"))
        first = date(yr, mo, 1)
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        last_day = (next_month - timedelta(days=1)).day
    except Exception:
        raise HTTPException(422, "invalid month format YYYY-MM")
    
    days = {}
    for d_num in range(1, last_day + 1):
        cur_date = date(yr, mo, d_num)
        avail = bool(_slots(db, cur_date, service))
        days[cur_date.isoformat()] = avail
    return {"month": month, "days": days}

@app.get("/api/public/slots")
def public_slots(day: date, service_id: int, db: Session = Depends(get_db)):
    service = db.query(BookingService).filter_by(id=service_id, is_active=True).first()
    if not service:
        raise HTTPException(404, "service not found")
    return {"day": day.isoformat(), "slots": _slots(db, day, service)}

PROOF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "proofs")


@app.post("/api/public/bookings/{reference}/proof")
async def upload_payment_proof(reference: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Store a guest's proof of payment against their booking reference.

    Kept small and strict: images and PDFs only, 8 MB at most, and the reference must
    exist so a stray upload cannot create a file with no booking behind it.
    """
    ref = (reference or "").strip().upper()[:32]
    booking = db.query(PublicBooking).filter(PublicBooking.booking_ref == ref).first()
    if not booking:
        raise HTTPException(404, "That booking reference was not found")

    data = await file.read()
    if not data:
        raise HTTPException(422, "The file was empty")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Please send a file smaller than 8 MB")

    ctype = (file.content_type or "").lower()
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
           "application/pdf": ".pdf"}.get(ctype)
    if not ext:
        raise HTTPException(415, "Send a photo (JPG or PNG) or a PDF of your payment")

    os.makedirs(PROOF_DIR, exist_ok=True)
    safe = re.sub(r"[^A-Z0-9_-]", "", ref)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{safe}-{stamp}{ext}"
    with open(os.path.join(PROOF_DIR, name), "wb") as fh:
        fh.write(data)

    booking.payment_proof = name
    booking.proof_uploaded_at = app_now()
    db.commit()
    return {"received": True, "reference": ref, "stored_as": name}


@app.post("/api/public/bookings", status_code=201)
def create_public_booking(payload: dict, db: Session = Depends(get_db)):
    try:
        service = db.query(BookingService).filter_by(id=int(payload["service_id"]), is_active=True).first()
        day = date.fromisoformat(payload["date"])
        start = time.fromisoformat(payload["start_time"])
        name = str(payload["full_name"]).strip()
        email = str(payload["email"]).strip().lower()
        phone = str(payload["phone_whatsapp"]).strip()
        dob = date.fromisoformat(payload["date_of_birth"]) if payload.get("date_of_birth") else None
    except Exception:
        raise HTTPException(422, "Please complete all required booking details")
    
    if not service:
        raise HTTPException(404, "Service is no longer available")
    if len(name) < 2 or "@" not in email or not re.fullmatch(r"\+?[0-9][0-9 ()-]{7,18}", phone):
        raise HTTPException(422, "Enter a valid name, email and WhatsApp phone number")
    
    end_dt = datetime.combine(day, start) + timedelta(minutes=service.duration_minutes)
    _lock_booking_day(db, day)
    if start.strftime("%H:%M") not in _slots(db, day, service):
        raise HTTPException(409, "That time was just booked. Please choose another slot.")
    
    client = db.query(Client).filter(func.lower(Client.email) == email).first()
    if not client:
        client = Client(name=name, phone=phone, phone_whatsapp=phone, email=email, pillar="innerhealth",
                        notes=payload.get("notes", ""), date_of_birth=dob,
                        gender=payload.get("gender"), medical_notes=payload.get("medical_notes", ""))
        db.add(client)
        db.flush()
    else:
        client.name = name
        client.phone = phone
        client.phone_whatsapp = phone
        if dob: client.date_of_birth = dob
        if payload.get("gender"): client.gender = payload["gender"]
        if payload.get("notes"): client.notes = payload["notes"]
        if payload.get("medical_notes"): client.medical_notes = payload["medical_notes"]
    
    booking = PublicBooking(
        client_id=client.id, service_id=service.id, booking_date=day, start_time=start,
        end_time=end_dt.time(), status="confirmed" if service.deposit <= 0 else "pending_deposit", token_hash="pending",
        total_fee=service.price, deposit_paid=service.deposit if service.deposit <= 0 else 0,
        balance_due=max(0, service.price - service.deposit), payment_method_balance="unpaid", notes=payload.get("notes", "")
    )
    db.add(booking)
    try:
        db.flush()
        token = _manage_token(booking.id)
        booking.token_hash = hashlib.sha256(token.encode()).hexdigest()
        booking.booking_ref = f"SCN-{1000 + booking.id}"
        db.commit()
        emit("booking.created")
    except Exception:
        db.rollback()
        raise HTTPException(409, "That time was just booked. Please choose another slot.")
    
    _notify(client, service, datetime.combine(day, start), token)
    payment_url = _deposit_checkout_url(booking, token)
    return {
        "id": booking.id, "reference": booking.booking_ref, "token": token, "status": booking.status,
        "service": service.name, "date": day.isoformat(), "start_time": start.strftime("%H:%M"),
        "end_time": booking.end_time.strftime("%H:%M"), "deposit_required": service.deposit,
        "payment_url": payment_url, "manage_url": f"/manage/{token}"
    }

@app.post("/api/payments/deposit/confirm")
def payment_deposit_confirm(payload: dict, x_payment_secret: str = Header(default=""), db: Session = Depends(get_db)):
    secret = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
    if not secret or not hmac.compare_digest(x_payment_secret, secret):
        raise HTTPException(401, "invalid payment webhook credentials")
    b = db.query(PublicBooking).filter_by(booking_ref=payload.get("reference")).first()
    if not b:
        raise HTTPException(404, "booking not found")
    try:
        amount = float(payload.get("amount", 0))
    except (TypeError, ValueError):
        raise HTTPException(422, "invalid deposit amount")
    if abs(amount - b.service.deposit) > 0.005:
        raise HTTPException(422, "deposit amount does not match booking")
    if b.status == "cancelled":
        raise HTTPException(409, "booking has been cancelled")
    b.deposit_paid = amount
    b.status = "confirmed"
    db.commit()
    emit("booking.deposit_paid", booking_id=b.id)
    token = _manage_token(b.id)
    _notify(b.client, b.service, datetime.combine(b.booking_date, b.start_time), token)
    return {"ok": True, "reference": b.booking_ref, "status": b.status}

@app.get("/api/public/manage/{token}")
def manage_booking_info(token: str, db: Session = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    b = db.query(PublicBooking).filter_by(token_hash=digest).first()
    if not b:
        raise HTTPException(404, "Booking link expired or invalid")
    return {
        "reference": b.booking_ref or f"SCN-{1000+b.id}", "service": b.service.name, "date": b.booking_date.isoformat(),
        "start_time": b.start_time.strftime("%H:%M"), "status": b.status, "deposit_paid": b.deposit_paid,
        "deposit_required": b.service.deposit, "balance_due": b.balance_due,
        "payment_url": _deposit_checkout_url(b, token),
        "address": os.getenv("CLINIC_ADDRESS", "202 Robert Sobukwe Street, Esselen Towers, Sunnyside, Pretoria, 0002"),
        "bank_transfer": _bank_transfer_details(b.booking_ref or f"SCN-{1000+b.id}", b.service.deposit)
    }

@app.post("/api/public/manage/{token}/cancel")
def cancel_public_booking(token: str, db: Session = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    b = db.query(PublicBooking).filter_by(token_hash=digest).first()
    if not b:
        raise HTTPException(404, "Booking link expired or invalid")
    if b.booking_date < app_today() or b.status in ("cancelled", "completed"):
        raise HTTPException(409, "This booking can no longer be cancelled")
    b.status = "cancelled"
    db.commit()
    emit("booking.cancelled")
    return {"ok": True}

@app.get("/api/public/manage/{token}/slots")
def manage_booking_slots(token: str, day: date, db: Session = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    b = db.query(PublicBooking).filter_by(token_hash=digest).first()
    if not b:
        raise HTTPException(404, "Booking link expired or invalid")
    if b.status != "confirmed" or b.booking_date < app_today():
        raise HTTPException(409, "This booking can no longer be changed")
    return {"date": day.isoformat(), "slots": _slots(db, day, b.service, b.id)}

@app.post("/api/public/manage/{token}/reschedule")
def reschedule_public_booking(token: str, payload: dict, db: Session = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    b = db.query(PublicBooking).filter_by(token_hash=digest).first()
    if not b:
        raise HTTPException(404, "Booking link expired or invalid")
    if b.status != "confirmed" or b.booking_date < app_today():
        raise HTTPException(409, "This booking can no longer be changed")
    try:
        day = date.fromisoformat(payload["date"])
        start = time.fromisoformat(payload["start_time"])
    except Exception:
        raise HTTPException(422, "Choose a valid date and time")
    _lock_booking_day(db, day)
    if start.strftime("%H:%M") not in _slots(db, day, b.service, b.id) and not (day == b.booking_date and start == b.start_time):
        raise HTTPException(409, "That time is no longer available. Choose another slot.")
    b.booking_date = day
    b.start_time = start
    b.end_time = (datetime.combine(day, start) + timedelta(minutes=b.service.duration_minutes)).time()
    db.commit()
    emit("booking.rescheduled")
    _notify(b.client, b.service, datetime.combine(day, start), token)
    return {"ok": True}

@app.get("/api/public/manage/{token}/calendar.ics")
def booking_ics(token: str, db: Session = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    b = db.query(PublicBooking).filter_by(token_hash=digest).first()
    if not b:
        raise HTTPException(404, "Booking link expired or invalid")
    start = datetime.combine(b.booking_date, b.start_time).strftime("%Y%m%dT%H%M%S")
    end = datetime.combine(b.booking_date, b.end_time).strftime("%Y%m%dT%H%M%S")
    ics = f"BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:booking-{b.id}@innerhealth\nDTSTART:{start}\nDTEND:{end}\nSUMMARY:{b.service.name}\nEND:VEVENT\nEND:VCALENDAR"
    return Response(ics, media_type="text/calendar", headers={"Content-Disposition": f"attachment; filename=booking-{b.id}.ics"})

# ---------------------------------------------------------------------------
# Admin APIs
# ---------------------------------------------------------------------------

@app.post("/api/admin/change-password", dependencies=[Depends(require_admin)])
def change_admin_password(payload: AdminPasswordChange, db: Session = Depends(get_db)):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", payload.new_password.encode(), salt, 310_000).hex()
    credential = db.query(AdminCredential).filter_by(id=1).first()
    if credential is None:
        credential = AdminCredential(id=1, password_hash=digest, password_salt=salt.hex())
        db.add(credential)
    else:
        credential.password_hash = digest
        credential.password_salt = salt.hex()
    db.commit()
    return {"status": "ok", "message": "Admin password updated"}

@app.get("/api/admin/bookings", dependencies=[Depends(require_admin)])
def admin_bookings(from_date: Optional[date] = None, to_date: Optional[date] = None, db: Session = Depends(get_db)):
    q = db.query(PublicBooking)
    if from_date: q = q.filter(PublicBooking.booking_date >= from_date)
    if to_date: q = q.filter(PublicBooking.booking_date <= to_date)
    return [
        {"id": b.id, "reference": b.booking_ref or f"SCN-{1000+b.id}", "date": b.booking_date.isoformat(),
         "start_time": b.start_time.strftime("%H:%M"), "end_time": b.end_time.strftime("%H:%M"),
         "status": b.status, "client": b.client.name, "email": b.client.email, "phone": b.client.phone,
         "service": b.service.name, "total_fee": b.total_fee, "deposit_paid": b.deposit_paid,
         "balance_due": b.balance_due, "balance_paid": b.balance_paid,
         "payment_method_balance": b.payment_method_balance, "ai_scan_status": b.ai_scan_status,
         "client_id": b.client_id}
        for b in q.order_by(PublicBooking.booking_date, PublicBooking.start_time).all()
    ]

@app.patch("/api/admin/bookings/{booking_id}", dependencies=[Depends(require_admin)])
def admin_booking_status(booking_id: int, payload: dict, db: Session = Depends(get_db)):
    b = db.query(PublicBooking).filter_by(id=booking_id).first()
    if not b:
        raise HTTPException(404, "booking not found")
    if "status" in payload and payload.get("status") not in ["pending_deposit", "confirmed", "arriving_soon", "in_scan", "completed", "cancelled", "no_show"]:
        raise HTTPException(422, "invalid status")
    if payload.get("status") in ["confirmed", "arriving_soon", "in_scan"] and b.deposit_paid < b.service.deposit:
        raise HTTPException(409, "Confirm the deposit before checking in")
    if payload.get("deposit_received"):
        b.deposit_paid = b.service.deposit
        if b.status == "pending_deposit":
            b.status = "confirmed"
    if "ai_scan_status" in payload:
        if payload["ai_scan_status"] not in ["not_started", "queued_in_cloud", "processing_local_ai", "report_ready"]:
            raise HTTPException(422, "invalid AI scan status")
        b.ai_scan_status = payload["ai_scan_status"]
    if "ai_scan_input" in payload:
        b.ai_scan_input = str(payload["ai_scan_input"])[:50000]
    if "status" in payload:
        b.status = payload["status"]
    db.commit()
    emit("booking.status", booking_id=b.id)
    return {"ok": True}

@app.post("/api/admin/bookings/{booking_id}/collect-balance", dependencies=[Depends(require_admin)])
def collect_booking_balance(booking_id: int, payload: dict, db: Session = Depends(get_db)):
    b = db.query(PublicBooking).filter_by(id=booking_id).first()
    if not b:
        raise HTTPException(404, "booking not found")
    method = payload.get("payment_method")
    if method not in ["cash", "card", "eft"]:
        raise HTTPException(422, "choose cash, card or eft")
    b.balance_paid = True
    b.balance_due = 0
    b.payment_method_balance = method
    if b.status != "cancelled":
        b.status = "completed"
    db.commit()
    emit("booking.balance_paid", booking_id=b.id)
    return {"ok": True, "total_collected": b.deposit_paid + b.total_fee - b.service.deposit}

@app.patch("/api/admin/bookings/{booking_id}/deposit", dependencies=[Depends(require_admin)])
def mark_deposit_paid(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(PublicBooking).filter_by(id=booking_id).first()
    if not b:
        raise HTTPException(404, "booking not found")
    b.deposit_paid = b.service.deposit
    b.status = "confirmed"
    db.commit()
    emit("booking.deposit_paid", booking_id=b.id)
    return {"ok": True}

@app.post("/api/admin/walk-in-sales", dependencies=[Depends(require_admin)])
def create_walk_in_sale(payload: dict, db: Session = Depends(get_db)):
    amount = float(payload.get("amount_zar", 0))
    method = payload.get("payment_method", "cash")
    if amount <= 0 or method not in ["cash", "card", "eft"]:
        raise HTTPException(422, "Enter a valid amount and payment method")
    sale = WalkInSale(
        client_id=payload.get("client_id"),
        item_name=str(payload.get("item_name", "Supplement / Addon")),
        amount_zar=amount,
        payment_method=method,
    )
    db.add(sale)
    db.commit()
    emit("sale.created", amount=payload.get("amount_zar"))
    return {"ok": True, "id": sale.id}

@app.post("/api/admin/bookings/manual", dependencies=[Depends(require_admin)])
def create_manual_scan_booking(payload: dict, db: Session = Depends(get_db)):
    try:
        service = db.query(BookingService).filter_by(id=int(payload["service_id"])).first()
        day = date.fromisoformat(payload["date"])
        start = time.fromisoformat(payload["start_time"])
        name = str(payload["name"]).strip()
        phone = str(payload.get("phone", "")).strip()
        email = str(payload.get("email", "")).strip().lower()
    except Exception:
        raise HTTPException(422, "Enter a client, service, date and time")
    
    _lock_booking_day(db, day)
    end = (datetime.combine(day, start) + timedelta(minutes=service.duration_minutes)).time()
    if _active_overlap(db, day, start, end):
        raise HTTPException(409, "That time overlaps another booking")
    
    client = db.query(Client).filter(func.lower(Client.email) == email).first() if email else None
    if not client:
        client = Client(name=name, phone=phone, phone_whatsapp=phone, email=email or None,
                        pillar="innerhealth", medical_notes=payload.get("medical_notes", ""))
        db.add(client)
        db.flush()
    
    received = bool(payload.get("deposit_received")) or service.deposit <= 0
    b = PublicBooking(
        client_id=client.id, service_id=service.id, booking_date=day, start_time=start, end_time=end,
        total_fee=service.price, deposit_paid=service.deposit if received else 0,
        balance_due=max(0, service.price - service.deposit), payment_method_balance="unpaid", status="confirmed" if received else "pending_deposit",
        token_hash="pending", notes=payload.get("notes", ""), ai_scan_input=payload.get("ai_scan_input")
    )
    db.add(b)
    db.flush()
    b.booking_ref = f"SCN-{1000 + b.id}"
    token = _manage_token(b.id)
    b.token_hash = hashlib.sha256(token.encode()).hexdigest()
    db.commit()
    emit("booking.created")
    _notify(client, service, datetime.combine(day, start), token)
    return {"id": b.id, "booking_ref": b.booking_ref}

@app.get("/api/admin/scan-dashboard", dependencies=[Depends(require_admin)])
def scan_dashboard(day: Optional[date] = None, search: Optional[str] = None, db: Session = Depends(get_db)):
    selected_day = day or app_today()
    today = app_today()
    now = app_now()
    month_start = today.replace(day=1)
    
    schedule_rows = db.query(PublicBooking).filter(PublicBooking.booking_date == selected_day).order_by(PublicBooking.start_time).all()
    today_rows = db.query(PublicBooking).filter(PublicBooking.booking_date == today).all()
    month_rows = db.query(PublicBooking).filter(PublicBooking.booking_date >= month_start, PublicBooking.booking_date <= today).all()
    month_sales = db.query(WalkInSale).filter(WalkInSale.sold_at >= datetime.combine(month_start, time.min), WalkInSale.sold_at <= now).all()
    today_sales = db.query(WalkInSale).filter(WalkInSale.sold_at >= datetime.combine(today, time.min), WalkInSale.sold_at <= now).all()
    all_bookings = db.query(PublicBooking).all()
    all_sales = db.query(WalkInSale).all()

    month_keys = [month_start]
    for _ in range(11):
        month_keys.append((month_keys[-1] - timedelta(days=1)).replace(day=1))
    month_keys = sorted(month_keys)
    
    analytics = []
    for m in month_keys:
        end = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        rows = [b for b in all_bookings if m <= b.booking_date < end]
        sales = [s for s in all_sales if m <= s.sold_at.date() < end]
        analytics.append({
            "month": m.strftime("%b %Y"),
            "bookings": len(rows),
            "revenue": round(sum(b.deposit_paid + (b.total_fee - b.service.deposit if b.balance_paid else 0) for b in rows) + sum(s.amount_zar for s in sales), 2)
        })

    peak_hours = []
    peak_days = []
    for hour in range(9, 17):
        peak_hours.append({"hour": f"{hour:02d}:00", "count": sum(1 for b in all_bookings if b.start_time.hour == hour)})
    for weekday in range(7):
        peak_days.append({"day": WEEKDAYS[weekday][:3], "count": sum(1 for b in all_bookings if b.booking_date.weekday() == weekday)})

    paid_today = sum(b.deposit_paid + (b.total_fee - b.service.deposit if b.balance_paid else 0) for b in today_rows) + sum(s.amount_zar for s in today_sales)
    paid_month = sum(b.deposit_paid + (b.total_fee - b.service.deposit if b.balance_paid else 0) for b in month_rows) + sum(s.amount_zar for s in month_sales)
    
    agent = db.query(AIAgentHeartbeat).order_by(AIAgentHeartbeat.last_seen.desc()).first()
    ai_online = bool(agent and (now - agent.last_seen).total_seconds() < 120)

    next_bookings = [b for b in today_rows if datetime.combine(today, b.start_time) >= now and b.status not in ("cancelled", "completed", "no_show")]
    next_b = next_bookings[0] if next_bookings else None
    attention = sum(1 for b in today_rows if b.status in ("pending_deposit", "no_show", "cancelled"))

    clients = []
    for c in db.query(Client).order_by(Client.name).all():
        rows = [b for b in all_bookings if b.client_id == c.id]
        if search and search.lower() not in (c.name + " " + (c.phone or "") + " " + (c.email or "") + " " + " ".join(b.booking_ref or "" for b in rows)).lower():
            continue
        last = max((b.booking_date for b in rows), default=None)
        visits = len([b for b in rows if b.status == "completed"])
        spend = sum(b.deposit_paid + (b.total_fee - b.service.deposit if b.balance_paid else 0) for b in rows)
        clients.append({
            "id": c.id, "name": c.name, "phone": c.phone_whatsapp or c.phone, "email": c.email,
            "medical_notes": c.medical_notes or c.notes,
            "date_of_birth": c.date_of_birth.isoformat() if c.date_of_birth else None, "gender": c.gender,
            "visits": visits, "spend": round(spend, 2),
            "last_visit": last.isoformat() if last else None,
            "at_risk": bool(last and (today - last).days >= 60),
            "loyalty": "VIP" if spend >= 3000 else "Regular" if visits >= 3 else "New Client"
        })

    return {
        "date": selected_day.isoformat(),
        "today_revenue": round(paid_today, 2),
        "month_revenue": round(paid_month, 2),
        "today_deposits": sum(b.deposit_paid for b in today_rows),
        "today_pending_balances": sum(b.balance_due for b in today_rows if not b.balance_paid and b.deposit_paid > 0),
        "completed_scans": sum(b.status == "completed" for b in today_rows),
        "upcoming_confirmed": sum(b.status in ("confirmed", "arriving_soon") for b in today_rows),
        "avg_revenue_per_client": round(paid_month / max(1, len(set(b.client_id for b in month_rows))), 2),
        "confirmed_today": sum(b.status in ("confirmed", "arriving_soon", "in_scan") for b in today_rows),
        "attention_count": attention,
        "ai_agent_online": ai_online,
        "ai_agent_model": agent.model if agent else "offline",
        "next_incoming": ({"name": next_b.client.name, "minutes": max(0, int((datetime.combine(today, next_b.start_time) - now).total_seconds() / 60)), "balance_due": next_b.balance_due, "ref": next_b.booking_ref} if next_b else None),
        "schedule": [
            {"id": b.id, "reference": b.booking_ref or f"SCN-{1000+b.id}", "client_id": b.client_id, "client": b.client.name,
             "phone": b.client.phone, "email": b.client.email, "date": b.booking_date.isoformat(),
             "start": b.start_time.strftime("%H:%M"), "end": b.end_time.strftime("%H:%M"), "status": b.status,
             "service": b.service.name, "total_fee": b.total_fee, "deposit_paid": b.deposit_paid,
             "balance_due": b.balance_due, "balance_paid": b.balance_paid, "payment_method_balance": b.payment_method_balance,
             "ai_scan_status": b.ai_scan_status, "ai_scan_report": b.ai_scan_report, "scan_input": b.ai_scan_input,
             "notes": b.notes or b.client.medical_notes, "visits": sum(x.client_id == b.client_id and x.status == "completed" for x in all_bookings),
             "spend": round(sum(x.deposit_paid + (x.total_fee - x.service.deposit if x.balance_paid else 0) for x in all_bookings if x.client_id == b.client_id), 2)}
            for b in schedule_rows
        ],
        "analytics": analytics,
        "clients": clients,
        "addons_today": sum(s.amount_zar for s in today_sales),
        "addons_month": sum(s.amount_zar for s in month_sales),
        "monthly_deposits": sum(b.deposit_paid for b in month_rows),
        "monthly_balances": sum(b.total_fee - b.service.deposit for b in month_rows if b.balance_paid),
        "monthly_pending_balances": sum(b.balance_due for b in month_rows if b.deposit_paid > 0 and not b.balance_paid),
        "peak_month": max(analytics, key=lambda x: x["bookings"]) if analytics else None,
        "peak_revenue_month": max(analytics, key=lambda x: x["revenue"]) if analytics else None,
        "peak_hours": peak_hours,
        "peak_days": peak_days,
    }

@app.get("/api/admin/booking-services", dependencies=[Depends(require_admin)])
def admin_services(db: Session = Depends(get_db)):
    return [
        {"id": s.id, "name": s.name, "description": s.description, "duration_minutes": s.duration_minutes,
         "price": s.price, "deposit": s.deposit, "is_active": s.is_active}
        for s in db.query(BookingService).all()
    ]

@app.post("/api/admin/booking-services", dependencies=[Depends(require_admin)])
def admin_create_service(payload: dict, db: Session = Depends(get_db)):
    s = BookingService(
        name=payload["name"],
        description=payload.get("description", ""),
        duration_minutes=int(payload.get("duration_minutes", 45)),
        price=float(payload.get("price", 450)),
        deposit=float(payload.get("deposit", 150)),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(s)
    db.commit()
    emit("service.created")
    return {"id": s.id}

@app.put("/api/admin/booking-services/{service_id}", dependencies=[Depends(require_admin)])
def admin_update_service(service_id: int, payload: dict, db: Session = Depends(get_db)):
    s = db.query(BookingService).filter_by(id=service_id).first()
    if not s:
        raise HTTPException(404, "service not found")
    for k in ["name", "description", "duration_minutes", "price", "deposit", "is_active"]:
        if k in payload:
            setattr(s, k, payload[k])
    db.commit()
    emit("service.updated")
    return {"id": s.id}

@app.get("/api/admin/availability", dependencies=[Depends(require_admin)])
def admin_availability(db: Session = Depends(get_db)):
    return [
        {"day_of_week": r.day_of_week, "is_working_day": r.is_working_day,
         "start_time": r.start_time.strftime("%H:%M") if r.start_time else "",
         "end_time": r.end_time.strftime("%H:%M") if r.end_time else ""}
        for r in db.query(AvailabilityRule).order_by(AvailabilityRule.day_of_week).all()
    ]

@app.put("/api/admin/availability/{weekday}", dependencies=[Depends(require_admin)])
def admin_update_availability(weekday: int, payload: dict, db: Session = Depends(get_db)):
    r = db.query(AvailabilityRule).filter_by(day_of_week=weekday).first()
    if not r:
        r = AvailabilityRule(day_of_week=weekday)
        db.add(r)
    r.is_working_day = bool(payload.get("is_working_day"))
    r.start_time = time.fromisoformat(payload["start_time"]) if payload.get("start_time") else None
    r.end_time = time.fromisoformat(payload["end_time"]) if payload.get("end_time") else None
    db.commit()
    emit("availability.updated")
    return {"ok": True}

@app.get("/api/admin/blocked-dates", dependencies=[Depends(require_admin)])
def admin_blocked_dates(db: Session = Depends(get_db)):
    return [{"id": b.id, "date": b.date.isoformat(), "reason": b.reason} for b in db.query(BlockedDate).order_by(BlockedDate.date).all()]

@app.post("/api/admin/blocked-dates", dependencies=[Depends(require_admin)])
def add_blocked_date(payload: dict, db: Session = Depends(get_db)):
    d = date.fromisoformat(payload["date"])
    b = db.query(BlockedDate).filter_by(date=d).first()
    if b:
        b.reason = payload.get("reason", "")
    else:
        db.add(BlockedDate(date=d, reason=payload.get("reason", "")))
    db.commit()
    emit("availability.updated")
    return {"ok": True}

@app.delete("/api/admin/blocked-dates/{blocked_id}", dependencies=[Depends(require_admin)])
def delete_blocked_date(blocked_id: int, db: Session = Depends(get_db)):
    b = db.query(BlockedDate).filter_by(id=blocked_id).first()
    if b:
        db.delete(b)
        db.commit()
        emit("availability.updated")
    return {"ok": True}

@app.post("/api/admin/reminders/run", dependencies=[Depends(require_admin)])
def run_booking_reminders(db: Session = Depends(get_db)):
    now = app_now()
    sent = 0
    for b in db.query(PublicBooking).filter_by(status="confirmed").all():
        when = datetime.combine(b.booking_date, b.start_time)
        hours = (when - now).total_seconds() / 3600
        field = "reminder_24h_sent" if 23 <= hours <= 25 and not b.reminder_24h_sent else "reminder_2h_sent" if 1 <= hours <= 3 and not b.reminder_2h_sent else None
        if field:
            _notify(b.client, b.service, when, _manage_token(b.id))
            setattr(b, field, True)
            sent += 1
    db.commit()
    emit("reminders.run")
    return {"sent": sent}

# ---------------------------------------------------------------------------
# AI Agent Worker Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/agent/heartbeat", dependencies=[Depends(require_ai_agent)])
def agent_heartbeat(payload: dict, db: Session = Depends(get_db)):
    model = payload.get("model", "llama3.2")
    hb = db.query(AIAgentHeartbeat).filter_by(model=model).first()
    if hb:
        hb.last_seen = app_now()
    else:
        db.add(AIAgentHeartbeat(model=model, last_seen=app_now()))
    db.commit()
    emit("agent.heartbeat")
    return {"status": "ok"}

@app.get("/api/agent/queue", dependencies=[Depends(require_ai_agent)])
def local_ai_queue(db: Session = Depends(get_db)):
    jobs = db.query(PublicBooking).filter(
        PublicBooking.status.in_(["confirmed", "arriving_soon", "in_scan"]),
        PublicBooking.ai_scan_status == "queued_in_cloud",
        PublicBooking.ai_scan_input.is_not(None)
    ).order_by(PublicBooking.booking_date, PublicBooking.start_time).limit(10).all()
    return [{"id": b.id, "reference": b.booking_ref, "client": b.client.name, "service": b.service.name, "scan_input": b.ai_scan_input} for b in jobs]

@app.patch("/api/agent/bookings/{booking_id}", dependencies=[Depends(require_ai_agent)])
def local_ai_update(booking_id: int, payload: dict, db: Session = Depends(get_db)):
    b = db.query(PublicBooking).filter_by(id=booking_id).first()
    if not b:
        raise HTTPException(404, "booking not found")
    status = payload.get("ai_scan_status")
    if status not in ["queued_in_cloud", "processing_local_ai", "report_ready"]:
        raise HTTPException(422, "invalid AI queue state")
    b.ai_scan_status = status
    if "report" in payload:
        b.ai_scan_report = str(payload["report"])[:20000]
    db.commit()
    emit("booking.scan_updated", booking_id=b.id)
    return {"ok": True}

# ---------------------------------------------------------------------------
# HTML Frontend Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request}, headers=NO_CACHE)

# HTML pages must never be served from a phone's cache: always revalidate.
NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/book", response_class=HTMLResponse)
def booking_page():
    return FileResponse(os.path.join(STATIC_DIR, "book.html"), headers=NO_CACHE)

@app.get("/manage/{token}", response_class=HTMLResponse)
def manage_page(token: str):
    return FileResponse(os.path.join(STATIC_DIR, "manage.html"), headers=NO_CACHE)

@app.get("/admin/bookings", response_class=HTMLResponse)
def admin_booking_page():
    return FileResponse(os.path.join(STATIC_DIR, "scan-dashboard.html"), headers=NO_CACHE)

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

APP_BUILD = os.getenv("APP_BUILD", "2026-11-19-tabs")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Business Hub", "build": APP_BUILD}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
