"""
Inner Health Consultation Center — Scan Center & Booking Management
"""

import os
import re
import json
import secrets
import hashlib
import hmac
import base64
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, date, time
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, Form, Depends, Header
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
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
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String(20), nullable=False)
    send_at = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    sent_at = Column(DateTime, nullable=True)
    message = Column(Text, nullable=False)


class CommandLog(Base):
    __tablename__ = "command_logs"

    id = Column(Integer, primary_key=True, index=True)
    raw = Column(Text, nullable=False)
    intent = Column(String(60), nullable=True)
    result = Column(Text, nullable=True)
    data = Column(Text, nullable=True)
    success = Column(Boolean, default=True)
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _seed_defaults()

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
    if os.getenv("SMTP_HOST") and client.email:
        try:
            import smtplib
            from email.message import EmailMessage
            mail = EmailMessage()
            mail["Subject"] = "Inner Health Appointment Confirmation"
            mail["From"] = os.getenv("SMTP_FROM") or os.getenv("CLINIC_EMAIL", "innerhealthconsult@gmail.com")
            mail["To"] = client.email
            mail.set_content(message)
            with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587")), timeout=8) as smtp:
                if os.getenv("SMTP_USER"):
                    smtp.starttls()
                    smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
                smtp.send_message(mail)
        except Exception as exc:
            print(f"Email notification failed: {exc}")
    
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
    return {"id": c.id, "name": c.name}

@app.delete("/api/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(404, "client not found")
    db.delete(c)
    db.commit()
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
    return {"id": a.id}

@app.patch("/api/appointments/{appt_id}/status")
def patch_appointment_status(appt_id: int, status: str, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not a:
        raise HTTPException(404, "appointment not found")
    a.status = status
    db.commit()
    return {"id": a.id, "status": a.status}

@app.delete("/api/appointments/{appt_id}")
def delete_appointment(appt_id: int, db: Session = Depends(get_db)):
    a = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not a:
        raise HTTPException(404, "appointment not found")
    db.delete(a)
    db.commit()
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
    return {"id": item.id}

@app.patch("/api/inventory/{item_id}/adjust")
def adjust_inventory(item_id: int, delta: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    item.quantity = max(0, item.quantity + delta)
    db.commit()
    return {"id": item.id, "quantity": item.quantity, "low": item.quantity <= item.reorder_level}

@app.delete("/api/inventory/{item_id}")
def delete_inventory(item_id: int, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}

@app.post("/api/contact-logs", status_code=201)
def create_contact_log(payload: ContactLogCreate, db: Session = Depends(get_db)):
    log = ContactLog(**payload.model_dump())
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"id": log.id}

@app.post("/api/service-records", status_code=201)
def create_service_record(payload: ServiceRecordCreate, db: Session = Depends(get_db)):
    s = ServiceRecord(**payload.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id}

@app.get("/api/reminders")
def list_reminders(db: Session = Depends(get_db)):
    rems = db.query(Reminder).order_by(Reminder.send_at.desc()).limit(20).all()
    return [{"id": r.id, "appointment_id": r.appointment_id, "channel": r.channel, "send_at": r.send_at.isoformat(), "status": r.status, "message": r.message} for r in rems]

@app.post("/api/reminders/generate")
def generate_reminders(db: Session = Depends(get_db)):
    return {"generated": 0}

@app.post("/api/reminders/send-all")
def send_all_reminders(db: Session = Depends(get_db)):
    return {"sent": 0}

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
    if slots:
        lines.append("Next open scan slots: " + "; ".join(f"{d} at {', '.join(v)}" for d, v in slots.items()) + ".")
    lines += [
        "Rules you must never break: you are not a doctor, you do not diagnose disease, prescribe medicine, interpret scan results or promise a cure. For anything clinical say the scan is reviewed with a qualified practitioner at the consultation.",
        "If asked something you do not know about the clinic, say you will have the team confirm on WhatsApp rather than inventing it.",
        "Only Inner Health matters. If asked about anything unrelated, gently bring the conversation back to booking a scan.",
        "Never promise a slot until the booking page confirms it: always send them to /book to pick a time.",
    ]
    return "\n".join(lines), slots


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


def _admin_answer(snapshot: Dict[str, Any], question: str, kind: str) -> str:
    """Deterministic first pass. The model only rephrases this; numbers stay exact."""
    money = snapshot["money"]
    bk = snapshot["bookings"]
    cl = snapshot["clients"]
    q = question.lower()

    if kind == "money" or any(w in q for w in ("revenue", "money", "takings", "earn", "income", "sales", "rand")):
        return (f"Today {_money(money['revenue_today'])}, this week {_money(money['revenue_this_week'])}, "
                f"this month {_money(money['revenue_this_month'])}. "
                f"Deposits still pending: {money['deposits_pending_count']} worth "
                f"{_money(money['deposits_pending_value'])}. "
                f"Balances outstanding: {money['balances_outstanding_count']} worth "
                f"{_money(money['balances_outstanding_value'])}.")

    if kind == "clients" or any(w in q for w in ("client", "lapsed", "come back", "win back", "dormant", "vip")):
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

    if any(w in q for w in ("today", "diary", "schedule", "upcoming", "next", "appointment", "tomorrow")):
        rows = bk["next_up"]
        head = f"{bk['today']} bookings today, {bk['upcoming_next_7_days']} in the next 7 days."
        if not rows:
            return head + " Nothing on the diary is upcoming."
        listing = "; ".join(f"{r['start']} {r['client']} ({r['status']})" for r in rows[:5])
        return head + " Next up: " + listing + "."

    return (f"Patients: {cl['total']}. Bookings: {bk['total']} ({bk['today']} today). "
            f"Revenue today {_money(money['revenue_today'])}, this month {_money(money['revenue_this_month'])}. "
            f"{money['deposits_pending_count']} deposits and {money['balances_outstanding_count']} balances still open.")


@app.post("/api/admin/ask", dependencies=[Depends(require_admin)])
def admin_ask(payload: dict, db: Session = Depends(get_db)):
    """Ask the admin agent about anything in the hub. Always answers, even with no model."""
    question = str(payload.get("question", "")).strip()[:600]
    kind = str(payload.get("kind", "auto"))[:20]
    if not question and kind == "auto":
        raise HTTPException(422, "Ask a question first")

    snapshot = _admin_snapshot(db)
    answer = _admin_answer(snapshot, question, kind)
    mode = "rules"

    try:
        system = (
            "You are the internal admin assistant for Inner Health Consultation Center, Pretoria. "
            "You answer the owner only. You are given FACTS and a DRAFT answer computed from the live database. "
            "Keep every number and name exactly as in the draft. Rewrite the draft into at most three short, "
            "clear sentences. Never invent a client, amount, phone number or date. If the draft does not answer "
            "the question, say what data is missing instead of guessing. No markdown."
        )
        user = ("FACTS:\n" + json.dumps(snapshot, ensure_ascii=False)[:6000]
                + "\n\nDRAFT ANSWER:\n" + answer
                + "\n\nQUESTION: " + (question or "Give the daily summary"))
        body = json.dumps({
            "model": ADMIN_MODEL,
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
                if len(polished) > 20:
                    answer = polished
                    mode = "model"
                break
            except Exception:
                continue
    except Exception:
        pass

    return {"answer": answer, "mode": mode, "facts": snapshot}


def _whatsapp_link(phone: Optional[str], message: str) -> str:
    digits = re.sub(r"[^0-9]", "", phone or "")
    if digits.startswith("0") and len(digits) >= 10:
        digits = "27" + digits[1:]
    return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"


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
    return {"ok": True, "total_collected": b.deposit_paid + b.total_fee - b.service.deposit}

@app.patch("/api/admin/bookings/{booking_id}/deposit", dependencies=[Depends(require_admin)])
def mark_deposit_paid(booking_id: int, db: Session = Depends(get_db)):
    b = db.query(PublicBooking).filter_by(id=booking_id).first()
    if not b:
        raise HTTPException(404, "booking not found")
    b.deposit_paid = b.service.deposit
    b.status = "confirmed"
    db.commit()
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
    return {"ok": True}

@app.delete("/api/admin/blocked-dates/{blocked_id}", dependencies=[Depends(require_admin)])
def delete_blocked_date(blocked_id: int, db: Session = Depends(get_db)):
    b = db.query(BlockedDate).filter_by(id=blocked_id).first()
    if b:
        db.delete(b)
        db.commit()
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
    return {"ok": True}

# ---------------------------------------------------------------------------
# HTML Frontend Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/book", response_class=HTMLResponse)
def booking_page():
    return FileResponse(os.path.join(STATIC_DIR, "book.html"))

@app.get("/manage/{token}", response_class=HTMLResponse)
def manage_page(token: str):
    return FileResponse(os.path.join(STATIC_DIR, "manage.html"))

@app.get("/admin/bookings", response_class=HTMLResponse)
def admin_booking_page():
    return FileResponse(os.path.join(STATIC_DIR, "scan-dashboard.html"))

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Business Hub"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
