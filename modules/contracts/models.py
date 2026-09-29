from sqlalchemy import text


def create_contracts_tables(conn):
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS contracts (
        id SERIAL PRIMARY KEY,
        contract_number TEXT,
        counterparty TEXT,
        inn TEXT,
        amount NUMERIC(18,2),
        start_date DATE,
        end_date DATE,
        status TEXT,
        matching_text TEXT,
        is_frame BOOLEAN DEFAULT FALSE,
        external_code TEXT UNIQUE,
        ответственный TEXT,
        цфо TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """))
    conn.execute(text(
        "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS ответственный TEXT;"
    ))
    conn.execute(text(
        "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS цфо TEXT;"
    ))
    conn.execute(text("""
    CREATE TABLE IF NOT EXISTS application_contracts (
        application_number VARCHAR(50),
        application_date DATE,
        contract_id INTEGER REFERENCES contracts(id),
        PRIMARY KEY (application_number, application_date, contract_id)
    );
    """))
    conn.execute(text(
        "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS условия_пролонгации TEXT;"
    ))