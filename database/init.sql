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
CREATE TYPE internship_track AS ENUM ('STANDARD', 'EMPLOYMENT', 'OWN_BUSINESS');

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

-- 4. Słownik efektów uczenia się (PRZENIESIONE WYŻEJ)
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

-- 5. Tabela pośrednia: zapisy studentów do praktyk
CREATE TABLE internship_enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    internship_id UUID NOT NULL REFERENCES internships(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    uopz_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status enrollment_status NOT NULL DEFAULT 'PENDING',
    track_type internship_track NOT NULL DEFAULT 'STANDARD',
    
    -- Terminy i ogólne
    termin_od DATE,
    termin_do DATE,
    specjalnosc VARCHAR(255),
    ubezpieczenie_nw BOOLEAN DEFAULT FALSE,
    
    -- Dane o firmie (tylko do tex)
    firma_nazwa VARCHAR(255),
    firma_adres VARCHAR(255),
    firma_miasto VARCHAR(255),
    firma_nip_krs VARCHAR(50),
    firma_upowazniony_osoba VARCHAR(255),
    firma_upowazniony_stanowisko VARCHAR(255),
    
    -- Dane ZOPZ (tylko do tex)
    zopz_imie_nazwisko VARCHAR(255),
    zopz_stanowisko VARCHAR(255),
    zopz_telefon VARCHAR(50),
    zopz_email VARCHAR(255),
    
    -- Dodatki dla ścieżek
    uzasadnienie_sciezki TEXT,
    zalaczniki_sciezki TEXT,
    
    -- Oceny z procesu ewaluacji
    ocena_sprawozdania NUMERIC(3,1),
    ocena_uopz NUMERIC(3,1),
    ocena_zopz NUMERIC(3,1),
    ocena_opisowa_uopz TEXT,
    ocena_opisowa_zopz TEXT,
    
    -- Pytania egzaminacyjne
    sprawdzian_pytanie_1 TEXT,
    sprawdzian_ocena_1 NUMERIC(3,1),
    sprawdzian_pytanie_2 TEXT,
    sprawdzian_ocena_2 NUMERIC(3,1),
    sprawdzian_pytanie_3 TEXT,
    sprawdzian_ocena_3 NUMERIC(3,1),

    total_hours_logged INTEGER DEFAULT 0,
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(internship_id, student_id)          -- student może być zapisany tylko raz do tej samej praktyki
);

-- 5a. Harmonogram praktyki studenta
CREATE TABLE internship_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE,
    learning_outcome_id INTEGER NOT NULL REFERENCES learning_outcomes(id),
    nazwa_dzialu VARCHAR(255) NOT NULL,
    przykladowe_prace TEXT NOT NULL,
    liczba_dni INTEGER NOT NULL DEFAULT 0
);

-- 5b. Sprawozdanie z praktyki (Zał. 7)
CREATE TABLE internship_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES internship_enrollments(id) ON DELETE CASCADE UNIQUE,
    charakterystyka_miejsca TEXT,
    opis_i_analiza TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
-- 9. Audit Log generowania i edycji dokumentów
-- ============================================================
CREATE TABLE document_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    enrollment_id UUID REFERENCES internship_enrollments(id) ON DELETE SET NULL,
    document_type VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Admin domyślny (hasło: admin123)
-- ============================================================
INSERT INTO users (email, password_hash, first_name, last_name, role, is_active, wymagana_zmiana_hasla)
VALUES (
    'admin@ans-elblag.pl',
    'scrypt:32768:8:1$AG9yKW4lzZpg7XXx$762ca3d9801b32fe2d05ed47de4abb5d1dbdb4312bfa1ef05312f4a8c567991ec25df6288d387fff62a85c148f0c42b20c5a0185b794cec80e7b1e909e10f4bf',
    'System',
    'Admin',
    'ADMIN',
    TRUE,
    FALSE
);