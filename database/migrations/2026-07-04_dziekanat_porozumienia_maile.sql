-- Migracja: rola DZIEKANAT + porozumienia grupowe + e-mail osoby upoważnionej
-- Uruchomienie na serwerze:
--   docker exec -i sop_db psql -U ans_admin -d ans_praktyki < database/migrations/2026-07-04_dziekanat_porozumienia_maile.sql
-- Uwaga: ALTER TYPE ... ADD VALUE nie może działać w bloku transakcji — psql
-- domyślnie wykonuje każdą instrukcję osobno (autocommit), więc plik jest bezpieczny.

-- ── 1. Rola DZIEKANAT ────────────────────────────────────────────
ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'DZIEKANAT' BEFORE 'ADMIN';

-- ── 2. E-mail osoby upoważnionej do podpisania porozumienia ──────
ALTER TABLE workplace_details
    ADD COLUMN IF NOT EXISTS company_authorized_email VARCHAR(255);

-- ── 3. Porozumienia z zakładami pracy ────────────────────────────
DO $$ BEGIN
    CREATE TYPE agreement_status AS ENUM ('SENT', 'FILLED', 'CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS internship_agreements (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name       VARCHAR(255) NOT NULL,
    company_address    VARCHAR(255),
    company_city       VARCHAR(255),
    company_tax_id     VARCHAR(50),
    recipient_name     VARCHAR(255) NOT NULL,
    recipient_position VARCHAR(255),
    recipient_email    VARCHAR(255) NOT NULL,
    token_hash         VARCHAR(64) NOT NULL UNIQUE,
    status             agreement_status NOT NULL DEFAULT 'SENT',
    created_by_id      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at         TIMESTAMP,
    filled_at          TIMESTAMP,
    signer_name        VARCHAR(255),
    signer_position    VARCHAR(255),
    company_notes      TEXT
);

CREATE TABLE IF NOT EXISTS agreement_enrollments (
    agreement_id  UUID NOT NULL REFERENCES internship_agreements(id)  ON DELETE CASCADE,
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    PRIMARY KEY (agreement_id, enrollment_id)
);

CREATE INDEX IF NOT EXISTS idx_agreements_status ON internship_agreements (status);
CREATE INDEX IF NOT EXISTS idx_agreement_enrollments_enrollment ON agreement_enrollments (enrollment_id);
