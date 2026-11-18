-- Reference PostgreSQL schema; SQLAlchemy metadata creates it for SQLite/PostgreSQL.
ALTER TABLE clients ADD COLUMN IF NOT EXISTS phone_whatsapp VARCHAR(40);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS date_of_birth DATE;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS gender VARCHAR(40);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS medical_notes TEXT;
CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY, name VARCHAR(120) NOT NULL, description TEXT DEFAULT '',
  duration_minutes INTEGER NOT NULL, price FLOAT NOT NULL DEFAULT 0,
  deposit FLOAT NOT NULL DEFAULT 150, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS availability_rules (
  id INTEGER PRIMARY KEY, day_of_week INTEGER NOT NULL UNIQUE,
  start_time TIME, end_time TIME, is_working_day BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS blocked_dates (
  id INTEGER PRIMARY KEY, date DATE NOT NULL UNIQUE, reason VARCHAR(240) DEFAULT ''
);
CREATE TABLE IF NOT EXISTS bookings (
  id INTEGER PRIMARY KEY, booking_ref VARCHAR(24) UNIQUE,
  client_id INTEGER NOT NULL REFERENCES clients(id), service_id INTEGER NOT NULL REFERENCES services(id),
  booking_date DATE NOT NULL, start_time TIME NOT NULL, end_time TIME NOT NULL,
  total_fee FLOAT NOT NULL DEFAULT 450, deposit_paid FLOAT NOT NULL DEFAULT 0,
  balance_due FLOAT NOT NULL DEFAULT 300, balance_paid BOOLEAN NOT NULL DEFAULT FALSE,
  payment_method_balance VARCHAR(20) NOT NULL DEFAULT 'unpaid',
  status VARCHAR(30) NOT NULL DEFAULT 'pending_deposit', ai_scan_status VARCHAR(30) NOT NULL DEFAULT 'queued_in_cloud',
  ai_scan_input TEXT, ai_scan_report TEXT, notes TEXT, token_hash VARCHAR(64) NOT NULL UNIQUE,
  reminder_24h_sent BOOLEAN NOT NULL DEFAULT FALSE, reminder_2h_sent BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS walk_in_sales (
  id INTEGER PRIMARY KEY, client_id INTEGER REFERENCES clients(id), item_name VARCHAR(160) NOT NULL,
  amount_zar FLOAT NOT NULL, payment_method VARCHAR(20) NOT NULL DEFAULT 'cash', sold_at TIMESTAMP NOT NULL
);
