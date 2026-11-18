"""Insert realistic demo clients, 12 months of scan bookings, today's LED states and sales.
Run only against a development database: `python seed_scan_demo.py`.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, time, date

import main
from main import (SessionLocal, Client, BookingService, PublicBooking, WalkInSale, app_today)

main.on_startup()
db = SessionLocal()
try:
    if db.query(PublicBooking).count():
        raise SystemExit("Bookings already exist; refusing to add duplicate demo data.")
    names = [
        ("Naledi Mokoena", "+27821234001", "naledi@example.test"),
        ("Thabo Nkosi", "+27821234002", "thabo@example.test"),
        ("Zanele Dlamini", "+27821234003", "zanele@example.test"),
        ("Lerato Khumalo", "+27821234004", "lerato@example.test"),
        ("Sipho Ndlovu", "+27821234005", "sipho@example.test"),
        ("Ayanda Maseko", "+27821234006", "ayanda@example.test"),
        ("Kagiso Molefe", "+27821234007", "kagiso@example.test"),
        ("Nomsa Zulu", "+27821234008", "nomsa@example.test"),
        ("Bongani Pillay", "+27821234009", "bongani@example.test"),
        ("Palesa van der Merwe", "+27821234010", "palesa@example.test"),
    ]
    genders=["female","male","female","female","male","female","male","female","male","female"]
    clients = [Client(name=n, phone=p, phone_whatsapp=p, email=e, pillar="innerhealth",
                      date_of_birth=date(1982+i, (i%12)+1, 10+i), gender=genders[i],
                      medical_notes="Demo intake only. Replace with client-provided information.") for i,(n,p,e) in enumerate(names)]
    db.add_all(clients); db.commit()
    service = db.query(BookingService).filter(BookingService.name.ilike("%full-body scan consultation%")).first()
    today = app_today(); month = today.replace(day=1)
    month_starts=[month]
    for _ in range(11): month_starts.append((month_starts[-1]-timedelta(days=1)).replace(day=1))
    month_starts.reverse()
    counts=[32,38,35,45,42,54,46,58,49,68,51,24]
    for m,count in zip(month_starts,counts):
        next_month=(m.replace(day=28)+timedelta(days=4)).replace(day=1)
        last_day=min(next_month-timedelta(days=1), today-timedelta(days=1)) if m==month else next_month-timedelta(days=1)
        slots=[]; d=m
        while d<=last_day:
            hours=range(9,17) if d.weekday()<5 else range(9,15)
            slots.extend((d,time(hour,0)) for hour in hours)
            d+=timedelta(days=1)
        if not slots: continue
        for i in range(count):
            booking_day,start=slots[i%len(slots)]
            client=clients[i%len(clients)]
            done=(i%7!=0)
            b=PublicBooking(client_id=client.id,service_id=service.id,booking_date=booking_day,
                start_time=start,end_time=(datetime.combine(booking_day,start)+timedelta(minutes=45)).time(),
                booking_ref=None,total_fee=450,deposit_paid=150,balance_due=0 if done else 300,
                balance_paid=done,payment_method_balance=("eft" if done else "unpaid"),
                status=("completed" if done else "no_show"),ai_scan_status=("report_ready" if done else "queued_in_cloud"),
                token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
                created_at=datetime.combine(booking_day,time(8,0)))
            db.add(b); db.flush(); b.booking_ref=f"SCN-{1000+b.id}"
    db.commit()
    # Five explicit states for the live floor, represented at distinct times.
    today_states=[("pending_deposit",time(9,0),0,"not_started"),
                  ("confirmed",time(10,0),150,"queued_in_cloud"),
                  ("arriving_soon",time(11,0),150,"queued_in_cloud"),
                  ("in_scan",time(13,0),150,"processing_local_ai"),
                  ("completed",time(14,0),150,"report_ready")]
    for i,(status,start,deposit,ai) in enumerate(today_states):
        client=clients[i]
        b=PublicBooking(client_id=client.id,service_id=service.id,booking_date=today,start_time=start,
            end_time=(datetime.combine(today,start)+timedelta(minutes=45)).time(),total_fee=450,
            deposit_paid=deposit,balance_due=0 if status=="completed" else (300 if deposit else 300),
            balance_paid=status=="completed",payment_method_balance="cash" if status=="completed" else "unpaid",
            status=status,ai_scan_status=ai,notes="Demo schedule record",
            token_hash=hashlib.sha256(secrets.token_bytes(32)).hexdigest())
        db.add(b); db.flush(); b.booking_ref=f"SCN-{1000+b.id}"
    db.add_all([WalkInSale(client_id=clients[0].id,item_name="Nutrition supplement",amount_zar=220,payment_method="card",sold_at=datetime.combine(today,time(9,30))),
                WalkInSale(client_id=clients[2].id,item_name="Printed scan report",amount_zar=50,payment_method="cash",sold_at=datetime.combine(today,time(10,30)))])
    db.commit()
    print(f"Seeded {len(clients)} demo clients, 12 months of scan history and five floor states.")
finally:
    db.close()
