-- ============================================================
-- System Praktyk Zawodowych — ANS Elbląg
-- Nowy schemat bazy danych
-- ============================================================

-- Upewnij się, że dostępne jest rozszerzenie pgcrypto (gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Typy wyliczeniowe
CREATE TYPE user_role AS ENUM ('STUDENT', 'UOPZ', 'ADMIN');
CREATE TYPE internship_status AS ENUM ('ACTIVE', 'INACTIVE');
CREATE TYPE enrollment_status AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED');
CREATE TYPE evaluation_result AS ENUM ('ACHIEVED', 'PARTIALLY_ACHIEVED', 'NOT_ACHIEVED');

-- 2. Użytkownicy
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    album_number VARCHAR(20),
    role user_role NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    wymagana_zmiana_hasla BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Praktyki (szablony tworzone przez admina)
CREATE TABLE internships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rok_uczelniany VARCHAR(9) NOT NULL,       -- np. '2023/2024'
    semestr VARCHAR(10) NOT NULL,              -- 'zimowy' lub 'letni'
    wymiar_godzin INTEGER NOT NULL DEFAULT 160,
    status internship_status NOT NULL DEFAULT 'INACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabela pośrednia: zapisy studentów do praktyk
CREATE TABLE internship_enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    internship_id UUID NOT NULL REFERENCES internships(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    uopz_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status enrollment_status NOT NULL DEFAULT 'PENDING',
    total_hours_logged INTEGER DEFAULT 0,
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(internship_id, student_id)          -- student może być zapisany tylko raz do tej samej praktyki
);

-- 5. Słownik efektów uczenia się
CREATE TABLE learning_outcomes (
    id SERIAL PRIMARY KEY,
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

-- 6. Dziennik praktyk (powiązany z zapisem, nie z praktyka-szablonem)
CREATE TABLE journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    entry_date DATE NOT NULL,
    duration_hours INTEGER NOT NULL CHECK (duration_hours > 0 AND duration_hours <= 8),
    description TEXT NOT NULL,
    learning_outcome_id INTEGER NOT NULL REFERENCES learning_outcomes(id),
    UNIQUE(enrollment_id, entry_date)
);

-- 7. Ewaluacje (powiązane z zapisem)
CREATE TABLE internship_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    learning_outcome_id INTEGER NOT NULL REFERENCES learning_outcomes(id),
    result evaluation_result NOT NULL,
    evaluator_notes TEXT
);

-- 8. Cache dokumentów
CREATE TABLE document_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    annex_type VARCHAR(10) NOT NULL,
    raw_tex_code TEXT NOT NULL,
    data_hash VARCHAR(64) NOT NULL,
    file_path VARCHAR(255) NOT NULL
);

-- ============================================================
-- TRIGGER: agregacja godzin na poziomie zapisu
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
-- Admin domyślny (hasło: admin123)
-- ============================================================
INSERT INTO users (email, password_hash, first_name, last_name, role, is_active, wymagana_zmiana_hasla)
VALUES (
    'admin@ans-elblag.pl',
    'scrypt:32768:8:1$MVO0GnsglSQucOms$dd638e95af8595eb370a91641948c14144d120a432d62780435b85b5eb575f8023d04f13b85b89e4b6ba8b4ce9a1f0ab430c92dba223914ecd7c5287b885d5e2',
    'System',
    'Admin',
    'ADMIN',
    TRUE,
    FALSE
);