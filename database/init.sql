-- ============================================================
-- System Praktyk Zawodowych — ANS Elbląg
-- Schemat bazy danych (polskie nazwy tabel i kolumn)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- 1. Typy wyliczeniowe
-- ============================================================

CREATE TYPE rola_uzytkownika AS ENUM ('STUDENT', 'UOPZ', 'ADMIN');
CREATE TYPE status_praktyki  AS ENUM ('ACTIVE', 'INACTIVE');
CREATE TYPE status_zapisu    AS ENUM (
    'PENDING',
    'AWAITING_APPROVAL',
    'COMMISSION_REVIEW',
    'DEAN_APPROVAL',
    'IN_PROGRESS',
    'COMPLETED',
    'REJECTED'
);
CREATE TYPE wynik_oceny    AS ENUM ('ACHIEVED', 'PARTIALLY_ACHIEVED', 'NOT_ACHIEVED');
CREATE TYPE sciezka_praktyki AS ENUM ('STANDARD', 'EMPLOYMENT', 'OWN_BUSINESS');

-- ============================================================
-- 2. Użytkownicy — tabela wspólna (JTI base)
-- ============================================================

CREATE TABLE uzytkownicy (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                 VARCHAR(255) UNIQUE NOT NULL,
    hash_hasla            VARCHAR(255) NOT NULL,
    imie                  VARCHAR(100) NOT NULL,
    nazwisko              VARCHAR(100) NOT NULL,
    rola                  rola_uzytkownika NOT NULL,
    aktywny               BOOLEAN DEFAULT TRUE,
    wymagana_zmiana_hasla BOOLEAN DEFAULT TRUE,
    utworzono             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Podtabele JTI ────────────────────────────────────────────

CREATE TABLE studenci (
    id           UUID PRIMARY KEY REFERENCES uzytkownicy(id) ON DELETE CASCADE,
    numer_albumu VARCHAR(20),
    plec         VARCHAR(1),         -- 'M' lub 'K'
    kierunek     VARCHAR(100),
    specjalnosc  VARCHAR(100),
    tryb_studiow VARCHAR(20)         -- 'stacjonarne' / 'niestacjonarne'
);

CREATE TABLE administratorzy (
    id UUID PRIMARY KEY REFERENCES uzytkownicy(id) ON DELETE CASCADE
);

CREATE TABLE opiekunowie_uczelniani (
    id UUID PRIMARY KEY REFERENCES uzytkownicy(id) ON DELETE CASCADE
);

-- ============================================================
-- 3. Firmy
-- ============================================================

CREATE TABLE firmy (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nazwa                VARCHAR(255) NOT NULL,
    adres                VARCHAR(255),
    miasto               VARCHAR(100),
    nip_krs              VARCHAR(50),
    ma_stala_umowe       BOOLEAN DEFAULT TRUE,
    aktywna              BOOLEAN DEFAULT TRUE,
    utworzono            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 4. Edycje praktyk (szablony tworzone przez admina)
-- ============================================================

CREATE TABLE praktyki (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rok_uczelniany VARCHAR(9)  NOT NULL,   -- np. '2024/2025'
    semestr        VARCHAR(10) NOT NULL,   -- 'zimowy' / 'letni'
    wymiar_godzin  INTEGER NOT NULL DEFAULT 160,
    status         status_praktyki NOT NULL DEFAULT 'INACTIVE',
    utworzono      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 5. Słownik efektów uczenia się
-- ============================================================

CREATE TABLE efekty_uczenia (
    id   SERIAL PRIMARY KEY,
    opis TEXT NOT NULL
);

INSERT INTO efekty_uczenia (opis) VALUES
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
-- 6. Zapisy studentów na edycje praktyk
-- ============================================================

CREATE TABLE zapisy_praktyk (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    praktyka_id  UUID NOT NULL REFERENCES praktyki(id)    ON DELETE CASCADE,
    student_id   UUID NOT NULL REFERENCES uzytkownicy(id) ON DELETE CASCADE,
    uopz_id      UUID          REFERENCES uzytkownicy(id) ON DELETE SET NULL,
    firma_id     UUID          REFERENCES firmy(id)       ON DELETE SET NULL,

    status   status_zapisu    NOT NULL DEFAULT 'PENDING',
    sciezka  sciezka_praktyki NOT NULL DEFAULT 'STANDARD',

    -- Terminy
    termin_od        DATE,
    termin_do        DATE,
    specjalnosc      VARCHAR(255),
    ubezpieczenie_nw BOOLEAN DEFAULT FALSE,

    -- Dane zakładu (kopiowane do dokumentów TeX)
    firma_nazwa                  VARCHAR(255),
    firma_adres                  VARCHAR(255),
    firma_miasto                 VARCHAR(255),
    firma_nip_krs                VARCHAR(50),
    firma_upowazniony_osoba      VARCHAR(255),
    firma_upowazniony_stanowisko VARCHAR(255),

    -- Dane ZOPZ
    zopz_imie_nazwisko VARCHAR(255),
    zopz_stanowisko    VARCHAR(255),
    zopz_telefon       VARCHAR(50),
    zopz_email         VARCHAR(255),

    -- Ścieżki B/C
    uzasadnienie_sciezki TEXT,
    zalaczniki_sciezki   TEXT,

    -- Oceny
    ocena_sprawozdania  NUMERIC(3,1),
    ocena_uopz          NUMERIC(3,1),
    ocena_zopz          NUMERIC(3,1),
    ocena_opisowa_uopz  TEXT,
    ocena_opisowa_zopz  TEXT,

    -- Sprawdzian
    sprawdzian_pytanie_1 TEXT,
    sprawdzian_ocena_1   NUMERIC(3,1),
    sprawdzian_pytanie_2 TEXT,
    sprawdzian_ocena_2   NUMERIC(3,1),
    sprawdzian_pytanie_3 TEXT,
    sprawdzian_ocena_3   NUMERIC(3,1),

    lacznie_godzin INTEGER DEFAULT 0,
    zapisano_o     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Komentarze procesowe
    komentarze_admina       TEXT,
    komentarze_uopz         TEXT,
    powiadomiono_studenta_o TIMESTAMP,

    -- Komisja (ścieżki B/C)
    komentarze_komisji  TEXT,
    decyzja_komisji     VARCHAR(20),   -- 'APPROVED' / 'REJECTED'
    decyzja_komisji_o   TIMESTAMP,

    -- Dziekan (ścieżki B/C)
    komentarze_dziekana TEXT,
    decyzja_dziekana    VARCHAR(20),   -- 'APPROVED' / 'REJECTED'
    decyzja_dziekana_o  TIMESTAMP,

    UNIQUE (praktyka_id, student_id)
);

-- ============================================================
-- 7. Harmonogram praktyki studenta
-- ============================================================

CREATE TABLE harmonogram_praktyk (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zapis_id          UUID NOT NULL REFERENCES zapisy_praktyk(id) ON DELETE CASCADE,
    efekt_id          INTEGER NOT NULL REFERENCES efekty_uczenia(id),
    nazwa_dzialu      VARCHAR(255) NOT NULL,
    przykladowe_prace TEXT NOT NULL,
    liczba_dni        INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- 8. Sprawozdanie z praktyki (Zał. 7)
-- ============================================================

CREATE TABLE sprawozdania (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zapis_id                UUID NOT NULL REFERENCES zapisy_praktyk(id) ON DELETE CASCADE UNIQUE,
    charakterystyka_miejsca TEXT,
    opis_i_analiza          TEXT,
    zaktualizowano          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 9. Dziennik praktyk
-- ============================================================

CREATE TABLE wpisy_dziennika (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zapis_id      UUID NOT NULL REFERENCES zapisy_praktyk(id) ON DELETE CASCADE,
    data_wpisu    DATE NOT NULL,
    liczba_godzin INTEGER NOT NULL CHECK (liczba_godzin > 0 AND liczba_godzin <= 8),
    opis          TEXT NOT NULL,
    UNIQUE (zapis_id, data_wpisu)
);

-- Tabela pośrednia: wpis dziennika ↔ efekty uczenia (wiele-do-wielu)
CREATE TABLE wpisy_efekty (
    wpis_id   UUID    NOT NULL REFERENCES wpisy_dziennika(id) ON DELETE CASCADE,
    efekt_id  INTEGER NOT NULL REFERENCES efekty_uczenia(id),
    PRIMARY KEY (wpis_id, efekt_id)
);

-- ============================================================
-- 10. Oceny efektów uczenia
-- ============================================================

CREATE TABLE oceny_praktyk (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zapis_id UUID    NOT NULL REFERENCES zapisy_praktyk(id) ON DELETE CASCADE,
    efekt_id INTEGER NOT NULL REFERENCES efekty_uczenia(id),
    wynik    wynik_oceny NOT NULL,
    uwagi    TEXT
);

-- ============================================================
-- 11. Log audytu dokumentów
-- ============================================================

CREATE TABLE logi_audytu_dokumentow (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    uzytkownik_id UUID REFERENCES uzytkownicy(id)  ON DELETE SET NULL,
    zapis_id      UUID REFERENCES zapisy_praktyk(id) ON DELETE SET NULL,
    typ_dokumentu VARCHAR(50) NOT NULL,
    akcja         VARCHAR(50) NOT NULL,
    szczegoly     TEXT,
    wykonano_o    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 12. Dokumenty przesłane przez studenta
-- ============================================================

CREATE TABLE dokumenty_przeslane (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zapis_id           UUID NOT NULL REFERENCES zapisy_praktyk(id) ON DELETE CASCADE,
    typ_dokumentu      VARCHAR(50)  NOT NULL,
    oryginalna_nazwa   VARCHAR(255) NOT NULL,
    zapisana_nazwa     VARCHAR(255) NOT NULL,
    sciezka_pliku      VARCHAR(500) NOT NULL,
    rozmiar_pliku      INTEGER NOT NULL,
    typ_mime           VARCHAR(100) NOT NULL,
    przeslano_o        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    przeslane_przez_id UUID REFERENCES uzytkownicy(id) ON DELETE SET NULL
);

-- ============================================================
-- 13. Indywidualne programy praktyk
-- ============================================================

CREATE TABLE programy_indywidualne (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zapis_id               UUID NOT NULL REFERENCES zapisy_praktyk(id) ON DELETE CASCADE UNIQUE,
    status                 VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    zatwierdzony_przez_uopz BOOLEAN DEFAULT FALSE,
    zatwierdzono_o         TIMESTAMP,
    komentarz_uopz         TEXT,
    utworzono              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 14. Numery pism administracyjnych
-- ============================================================

CREATE TABLE numery_pism (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zapis_id      UUID NOT NULL REFERENCES zapisy_praktyk(id) ON DELETE CASCADE,
    typ_dokumentu VARCHAR(50)  NOT NULL,
    numer         VARCHAR(100) NOT NULL,
    wygenerowano  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TRIGGER: aktualizacja sumy godzin w zapisie
-- ============================================================

CREATE OR REPLACE FUNCTION aktualizuj_lacznie_godzin()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE zapisy_praktyk
        SET lacznie_godzin = lacznie_godzin + NEW.liczba_godzin
        WHERE id = NEW.zapis_id;
    ELSIF TG_OP = 'UPDATE' THEN
        UPDATE zapisy_praktyk
        SET lacznie_godzin = lacznie_godzin - OLD.liczba_godzin + NEW.liczba_godzin
        WHERE id = NEW.zapis_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE zapisy_praktyk
        SET lacznie_godzin = lacznie_godzin - OLD.liczba_godzin
        WHERE id = OLD.zapis_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_aktualizuj_godziny
AFTER INSERT OR UPDATE OR DELETE ON wpisy_dziennika
FOR EACH ROW EXECUTE FUNCTION aktualizuj_lacznie_godzin();

-- ============================================================
-- Domyślny administrator (hasło: admin123)
-- ============================================================

INSERT INTO uzytkownicy (email, hash_hasla, imie, nazwisko, rola, aktywny, wymagana_zmiana_hasla)
VALUES (
    'admin@ans-elblag.pl',
    'scrypt:32768:8:1$AG9yKW4lzZpg7XXx$762ca3d9801b32fe2d05ed47de4abb5d1dbdb4312bfa1ef05312f4a8c567991ec25df6288d387fff62a85c148f0c42b20c5a0185b794cec80e7b1e909e10f4bf',
    'System',
    'Admin',
    'ADMIN',
    TRUE,
    FALSE
);

INSERT INTO administratorzy (id)
SELECT id FROM uzytkownicy WHERE email = 'admin@ans-elblag.pl';
