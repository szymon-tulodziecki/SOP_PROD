-- ============================================================
-- System Praktyk Zawodowych — ANS Elbląg
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- 1. Enum types
-- ============================================================

CREATE TYPE user_role        AS ENUM ('STUDENT', 'UOPZ', 'KOMISJA', 'DYREKTOR', 'ADMIN');
CREATE TYPE internship_status AS ENUM ('ACTIVE', 'INACTIVE');
CREATE TYPE enrollment_status AS ENUM (
    'PENDING',
    'AWAITING_APPROVAL',
    'REVISION_REQUIRED',
    'COMMISSION_REVIEW',
    'DIRECTOR_APPROVAL',
    'IN_PROGRESS',
    'COMPLETED',
    'REJECTED'
);
CREATE TYPE assessment_result AS ENUM ('ACHIEVED', 'PARTIALLY_ACHIEVED', 'NOT_ACHIEVED');
CREATE TYPE internship_path   AS ENUM ('STANDARD', 'EMPLOYMENT', 'OWN_BUSINESS');
CREATE TYPE event_type        AS ENUM (
    'ADMIN_KOMENTARZ',
    'UOPZ_KOMENTARZ',
    'POWIADOMIENIE_STUDENTA',
    'KOMISJA_DECYZJA',
    'DYREKTOR_DECYZJA'
);

-- ============================================================
-- 2. Users — shared base table (JTI)
-- ============================================================

CREATE TABLE users (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                   VARCHAR(255) UNIQUE NOT NULL,
    password_hash           VARCHAR(255) NOT NULL,
    first_name              VARCHAR(100) NOT NULL,
    last_name               VARCHAR(100) NOT NULL,
    role                    user_role NOT NULL,
    is_active               BOOLEAN DEFAULT TRUE,
    require_password_change BOOLEAN DEFAULT TRUE,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── JTI sub-tables ────────────────────────────────────────────

CREATE TABLE students (
    id             UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    album_number   VARCHAR(20),
    gender         VARCHAR(1),       -- 'M' or 'F'
    field_of_study VARCHAR(100),
    specialization VARCHAR(100),
    study_mode     VARCHAR(20),      -- 'full-time' / 'part-time'
    supervisor_id  UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE administrators (
    id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE university_mentors (
    id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE komisja_users (
    id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE dyrektor_users (
    id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================================
-- 3. Companies
-- ============================================================

CREATE TABLE companies (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  VARCHAR(255) NOT NULL,
    address               VARCHAR(255),
    city                  VARCHAR(100),
    tax_id                VARCHAR(50),
    has_standing_agreement BOOLEAN DEFAULT TRUE,
    is_active             BOOLEAN DEFAULT TRUE,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. Internship editions (created by admin)
-- ============================================================

CREATE TABLE internships (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    academic_year  VARCHAR(9)  NOT NULL,   -- e.g. '2024/2025'
    semester       VARCHAR(10) NOT NULL,   -- 'winter' / 'summer'
    required_hours INTEGER NOT NULL DEFAULT 160,
    status         internship_status NOT NULL DEFAULT 'INACTIVE',
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at     TIMESTAMP DEFAULT NULL
);

-- ============================================================
-- 5. Learning outcomes dictionary
-- ============================================================

CREATE TABLE learning_outcomes (
    id          SERIAL PRIMARY KEY,
    description TEXT NOT NULL
);

INSERT INTO learning_outcomes (description) VALUES
('01: Ma wiedzę na temat sposobu realizacji zadań inżynierskich dotyczących informatyki z zachowaniem standardów i norm technicznych'),
('02: Zna technologie, narzędzia, metody, techniki oraz sprzęt stosowane w informatyce'),
('03: Zna ekonomiczne, prawne skutki własnych działań podejmowanych w ramach praktyki oraz ograniczenia wynikające z prawa autorskiego i kodeksu pracy'),
('04: Zna zasady bezpieczeństwa pracy i ergonomii w zawodzie informatyka'),
('05: Pozyskuje informacje odnośnie technologii, metod, technik, sprzętu wymaganego do realizacji powierzonego zadania, posługując się rozmaitymi źródłami...'),
('06: W oparciu o kontakty ze środowiskiem inżynierskim zakładu, potrafi podnieść swoje kompetencje, wiedzę i umiejętności...'),
('07: Opracowuje dokumentację dotyczącą realizacji podejmowanych zadań w ramach praktyki, a także referuje ustnie prezentowane w niej zagadnienia'),
('08: Potrafi zidentyfikować problem informatyczny występujący w zakładzie pracy/instytucji, opisać go, przedstawić koncepcję rozwiązania i ją zrealizować.'),
('09: Potrafi rozwiązać rzeczywiste zadanie inżynierskie z zakresu działalności informatycznej zakładu pracy/instytucji stosując normy i standardy...'),
('10: Pracuje w zespole zajmującym się zawodowo branżą IT'),
('11: Przestrzega zasad etyki zawodowej i zgodnie z tymi zasadami korzysta z wiedzy i pomocy doświadczonych kolegów'),
('12: Kontaktując się z osobami spoza branży potrafi zarówno pozyskać od nich niezbędne informacje do realizacji planowanego zadania...'),
('13: Dostrzega w praktyce tempo deaktualizacji wiedzy informatycznej oraz skutki działalności informatyków w szczególności ekonomiczne i społeczne');

-- ============================================================
-- 6. Student enrollment records — core (immutable + process data)
-- ============================================================

CREATE TABLE internship_enrollments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    internship_id UUID NOT NULL REFERENCES internships(id)  ON DELETE CASCADE,
    student_id    UUID NOT NULL REFERENCES users(id)        ON DELETE CASCADE,
    supervisor_id UUID          REFERENCES users(id)        ON DELETE SET NULL,
    company_id    UUID          REFERENCES companies(id)    ON DELETE SET NULL,

    status         enrollment_status NOT NULL DEFAULT 'PENDING',
    path_type      internship_path   NOT NULL DEFAULT 'STANDARD',

    start_date         DATE,
    end_date           DATE,
    specialization     VARCHAR(255),
    accident_insurance BOOLEAN DEFAULT FALSE,

    total_hours_logged INTEGER   DEFAULT 0,
    enrolled_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (internship_id, student_id)
);

-- ============================================================
-- 7. Workplace details (form snapshot → TeX documents)
-- ============================================================

CREATE TABLE workplace_details (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE UNIQUE,

    -- Company data
    company_name                  VARCHAR(255),
    company_address               VARCHAR(255),
    company_zip                   VARCHAR(10),
    company_city                  VARCHAR(255),
    company_tax_id                VARCHAR(50),
    company_authorized_person     VARCHAR(255),
    company_authorized_position   VARCHAR(255),

    -- Workplace supervisor (ZOPZ) data
    workplace_supervisor_name     VARCHAR(255),
    workplace_supervisor_position VARCHAR(255),
    workplace_supervisor_phone    VARCHAR(50),
    workplace_supervisor_email    VARCHAR(255)
);

-- ============================================================
-- 8. Path justification (B/C paths only)
-- ============================================================

CREATE TABLE path_justifications (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE UNIQUE,
    justification      TEXT,
    attachments        TEXT,        -- file names/paths (JSON or newline-separated)
    employment_subtype VARCHAR(20)  -- 'WORK' or 'INTERNSHIP'
);

-- ============================================================
-- 9. Internship schedule
-- ============================================================

CREATE TABLE internship_schedules (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id   UUID    NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    outcome_id      INTEGER NOT NULL REFERENCES learning_outcomes(id),
    department_name VARCHAR(255) NOT NULL,
    example_tasks   TEXT        NOT NULL,
    days_count      INTEGER     NOT NULL DEFAULT 0
);

-- ============================================================
-- 10. Internship report (Załącznik 7)
-- ============================================================

CREATE TABLE internship_reports (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id        UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE UNIQUE,
    workplace_description TEXT,
    analysis             TEXT,
    skills               TEXT,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 11. Journal entries
-- ============================================================

CREATE TABLE journal_entries (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id  UUID    NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    entry_date     DATE    NOT NULL,
    duration_hours INTEGER NOT NULL CHECK (duration_hours > 0 AND duration_hours <= 8),
    description    TEXT    NOT NULL,
    UNIQUE (enrollment_id, entry_date)
);

-- Junction table: journal_entry ↔ learning_outcomes (many-to-many)
CREATE TABLE entry_outcomes (
    entry_id   UUID    NOT NULL REFERENCES journal_entries(id)   ON DELETE CASCADE,
    outcome_id INTEGER NOT NULL REFERENCES learning_outcomes(id),
    PRIMARY KEY (entry_id, outcome_id)
);

-- ============================================================
-- 12. Outcome assessments (by UOPZ)
-- ============================================================

CREATE TABLE outcome_assessments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id       UUID    NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    learning_outcome_id INTEGER NOT NULL REFERENCES learning_outcomes(id),
    result              assessment_result NOT NULL,
    notes               TEXT
);

-- ============================================================
-- 13. Examination (3 questions graded by UOPZ)
-- ============================================================

CREATE TABLE examinations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE UNIQUE,

    question_1 TEXT,
    grade_1    NUMERIC(3, 1),
    question_2 TEXT,
    grade_2    NUMERIC(3, 1),
    question_3 TEXT,
    grade_3    NUMERIC(3, 1),

    commission_chair    VARCHAR(200),
    commission_member_2 VARCHAR(200),
    commission_member_3 VARCHAR(200)
);

-- ============================================================
-- 14. Final grades
-- ============================================================

CREATE TABLE final_grades (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE UNIQUE,

    report_grade                  NUMERIC(3, 1),
    supervisor_grade              NUMERIC(3, 1),
    workplace_grade               NUMERIC(3, 1),
    supervisor_grade_description  TEXT,
    workplace_grade_description   TEXT,
    supervisor_notes              TEXT,
    workplace_notes               TEXT
);

-- ============================================================
-- 15. Process events — workflow log (commission, dean, comments)
-- ============================================================

CREATE TABLE process_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID          NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    event_type    event_type    NOT NULL,
    decision      VARCHAR(20),              -- 'APPROVED' / 'REJECTED' (nullable)
    comment       TEXT,
    executed_by_id UUID         REFERENCES users(id) ON DELETE SET NULL,
    executed_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_process_events_enrollment ON process_events (enrollment_id);
CREATE INDEX idx_process_events_type       ON process_events (enrollment_id, event_type);

-- ============================================================
-- 16. Document audit log
-- ============================================================

CREATE TABLE document_audit_logs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id)                   ON DELETE SET NULL,
    enrollment_id UUID REFERENCES internship_enrollments(id)  ON DELETE SET NULL,
    document_type VARCHAR(50)  NOT NULL,
    action        VARCHAR(50)  NOT NULL,
    details       TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 17. Uploaded documents
-- ============================================================

CREATE TABLE uploaded_documents (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id     UUID         REFERENCES internship_enrollments(id) ON DELETE SET NULL,
    document_type     VARCHAR(50)  NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename   VARCHAR(255) NOT NULL,
    file_path         VARCHAR(500) NOT NULL,
    file_size         INTEGER      NOT NULL,
    mime_type         VARCHAR(100) NOT NULL,
    uploaded_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    is_deleted        BOOLEAN NOT NULL DEFAULT FALSE
);

-- ============================================================
-- 18. Individual internship programs
-- ============================================================

CREATE TABLE individual_programs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id          UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE UNIQUE,
    status                 VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    approved_by_supervisor BOOLEAN DEFAULT FALSE,
    approved_at            TIMESTAMP,
    supervisor_comment     TEXT,
    created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 19. Administrative document numbers
-- ============================================================

CREATE TABLE document_numbers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID         NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    document_type VARCHAR(50)  NOT NULL,
    number        VARCHAR(100) NOT NULL,
    generated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE committee_outcome_evaluations (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id       UUID    NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    learning_outcome_id INTEGER NOT NULL REFERENCES learning_outcomes(id),
    result              assessment_result NOT NULL,
    notes               TEXT,
    UNIQUE (enrollment_id, learning_outcome_id)
);

-- ============================================================
-- TRIGGER: update total_hours_logged on journal entry changes
-- ============================================================

CREATE OR REPLACE FUNCTION update_total_hours()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE internship_enrollments
        SET total_hours_logged = total_hours_logged + NEW.duration_hours
        WHERE id = NEW.enrollment_id;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE internship_enrollments
        SET total_hours_logged = total_hours_logged - OLD.duration_hours + NEW.duration_hours
        WHERE id = NEW.enrollment_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE internship_enrollments
        SET total_hours_logged = total_hours_logged - OLD.duration_hours
        WHERE id = OLD.enrollment_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_total_hours
AFTER INSERT OR UPDATE OR DELETE ON journal_entries
FOR EACH ROW EXECUTE FUNCTION update_total_hours();

-- ============================================================
-- Predefiniowane konta (logowanie przez Microsoft)
-- password_hash = '' — konto MS nie używa hasła lokalnego
-- ============================================================

INSERT INTO users (email, password_hash, first_name, last_name, role, is_active, require_password_change)
VALUES
    ('admin@tulodzieckiallgmail.onmicrosoft.com',    '', 'Szymon',    'Tułodziecki', 'ADMIN',    TRUE, FALSE),
    ('uopz@tulodzieckiallgmail.onmicrosoft.com',     '', 'Piotr',     'Nowak',       'UOPZ',     TRUE, FALSE),
    ('komisja@tulodzieckiallgmail.onmicrosoft.com',  '', 'Joanna',    'Kamińska',    'KOMISJA',  TRUE, FALSE),
    ('dyrektor@tulodzieckiallgmail.onmicrosoft.com', '', 'Tomasz',    'Zając',       'DYREKTOR', TRUE, FALSE),
    ('12345@tulodzieckiallgmail.onmicrosoft.com',    '', 'Katarzyna', 'Kowalczyk',   'STUDENT',  TRUE, FALSE),
    ('21312@tulodzieckiallgmail.onmicrosoft.com',    '', 'Marek',     'Wiśniewski',  'STUDENT',  TRUE, FALSE),
    ('21313@tulodzieckiallgmail.onmicrosoft.com',    '', 'Anna',      'Kowalska',    'STUDENT',  TRUE, FALSE)
ON CONFLICT (email) DO NOTHING;

INSERT INTO administrators (id)
SELECT id FROM users WHERE email = 'admin@tulodzieckiallgmail.onmicrosoft.com'
ON CONFLICT DO NOTHING;

INSERT INTO university_mentors (id)
SELECT id FROM users WHERE email = 'uopz@tulodzieckiallgmail.onmicrosoft.com'
ON CONFLICT DO NOTHING;

INSERT INTO komisja_users (id)
SELECT id FROM users WHERE email = 'komisja@tulodzieckiallgmail.onmicrosoft.com'
ON CONFLICT DO NOTHING;

INSERT INTO dyrektor_users (id)
SELECT id FROM users WHERE email = 'dyrektor@tulodzieckiallgmail.onmicrosoft.com'
ON CONFLICT DO NOTHING;

-- Studenci z przypisanym opiekunem UOPZ
INSERT INTO students (id, album_number, gender, field_of_study, specialization, study_mode, supervisor_id)
SELECT u.id, '12345', 'F', 'Informatyka', 'Aplikacje sieciowe i mobilne', 'full-time',
       (SELECT id FROM users WHERE email = 'uopz@tulodzieckiallgmail.onmicrosoft.com')
FROM users u WHERE u.email = '12345@tulodzieckiallgmail.onmicrosoft.com'
ON CONFLICT DO NOTHING;

INSERT INTO students (id, album_number, gender, field_of_study, specialization, study_mode, supervisor_id)
SELECT u.id, '21312', 'M', 'Informatyka', 'Aplikacje sieciowe i mobilne', 'full-time',
       (SELECT id FROM users WHERE email = 'uopz@tulodzieckiallgmail.onmicrosoft.com')
FROM users u WHERE u.email = '21312@tulodzieckiallgmail.onmicrosoft.com'
ON CONFLICT DO NOTHING;

INSERT INTO students (id, album_number, gender, field_of_study, specialization, study_mode, supervisor_id)
SELECT u.id, '21313', 'F', 'Informatyka', 'Systemy informatyczne', 'full-time',
       (SELECT id FROM users WHERE email = 'uopz@tulodzieckiallgmail.onmicrosoft.com')
FROM users u WHERE u.email = '21313@tulodzieckiallgmail.onmicrosoft.com'
ON CONFLICT DO NOTHING;
