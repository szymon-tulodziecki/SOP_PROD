# SOP — Stan Refaktoryzacji i Plan Pracy

## Architektura

Flask + SQLAlchemy + Celery (PDF przez tex-service). Dwie aplikacje blueprintowe:
- `app_admin/` — panel pracownika (UOPZ, KOMISJA, DYREKTOR, ADMIN)
- `app_student/` — portal studenta
- `core/` — modele, repozytoria, serwisy (warstwa domenowa)

Reguła: **route → serwis → repozytorium → model**. Nie wolno omijać warstw.

---

## ✅ Wykonane pakiety

| Pakiet | Co zrobiono |
|--------|------------|
| 1 | Poprawiono bug `sample_tasks`, usunięto martwą `layouts/panel.html` |
| 2 | Dodano właściwości domenowe do `InternshipEnrollment` (`is_path_b`, `progress_percent`, itd.) |
| 3 | Stworzono `core/tlumaczenia.py`, podłączono do obu `__init__.py` |
| 4 | Usunięto polskie `@property` shimy z `firmy.py`, `praktyki.py`; usunięto wszystkie polskie aliasy klas z `core/modele/__init__.py` |
| 5 | Przeniesiono inline importy na poziom modułu w 7 plikach |
| 6 | `SerwisOceniania.get_pilne_oceny()`, `deadline_info()` — wyekstrahowano z `pulpit.py` i `ocenianie.py` |
| 8 | `importuj_z_csv`, `przygotuj_liste_ocen`, `buduj_kontekst(ZAL_8)`, `waliduj_oceny_efektow`, `waliduj_mozliwosc_zakonczenia`, `status_dla_studenta` — boskie metody podzielone na serwisy |
| 10 | Zmienne lokalne w route'ach: `strona→page`, `zgloszenia→applications`, `zapis→enrollment` (admin), `dostepne→available`, `zapisy_data→status_map`, `pilne_oceny→urgent_grades`; `ZapisNieIstnieje→EnrollmentNotFound` |

---

## 🔴 PRIORYTET 1 — Wyciek Abstrakcji (db.session w route'ach)

**Zasada:** route nie dotyka `db.session` ani `.query.` — deleguje do serwisu lub repozytorium.

### Nowe metody repozytoriów do dodania

**`RepozytoriumWpisow`** (`core/repozytoria/wpisy.py`):
- `znajdz_po_id(wpis_id)` → `db.session.get(JournalEntry, wpis_id)`
- `usun(wpis)` → `db.session.delete(wpis)`

**`RepozytoriumZapisow`** (`core/repozytoria/praktyki.py`):
- `znajdz_odrzucony(student_id, internship_id)` → query REJECTED enrollment
- `usun_zdarzenia_zapisu(enrollment_id)` → `ProcessEvent.delete()` bulk
- `ostatnie_zdarzenie(enrollment_id, event_type=None, decision=None)` → last ProcessEvent
- `zapisz_harmonogram(rows)` → `db.session.add_all(rows)`

**`RepozytoriumUzytkownikow`** (`core/repozytoria/uzytkownicy.py`):
- `aktywni_mentorzy()` → UniversityMentor ordered by last_name, first_name

**`RepozytoriumOcen`** (`core/repozytoria/oceny.py`):
- `dla_komisji(enrollment_id)` → CommitteeOutcomeEvaluation list
- `zapisz_ocene_komisji(enrollment_id, outcome_id, result, notes)` → upsert CommitteeOutcomeEvaluation

**`RepozytoriumDokumentowStudenta`** (`core/repozytoria/dokumenty.py`):
- `zapisz_log(log)` → `db.session.add(DocumentAuditLog(...))`
- `dokumenty_zapisu(enrollment_id)` → UploadedDocument list for enrollment

**`RepozytoriumLogow`** (`core/repozytoria/dokumenty.py`):
- `wszystkie_zdarzenia(filtr_typ=None, szukaj_user=None, limit=100)` → ProcessEvent list

### Pliki route do zaktualizowania (używają istniejących metod po dodaniu nowych)

- `app_admin/routes/dokumenty.py` — `db.session.add(DocumentAuditLog)` → `_repo_docs.zapisz_log`
- `app_admin/routes/logi.py` — `ProcessEvent.query.order_by` → `_repo_logow.wszystkie_zdarzenia`
- `app_admin/routes/ocenianie.py` — 4× `db.session.get(InternshipEnrollment)` → `_repo_zapisow.znajdz_po_id`; `db.session.execute(UniversityMentor)` → `_repo_uzytk.aktywni_mentorzy`; `db.session.add(OutcomeAssessment)` → `_repo_assessments.zapisz`
- `app_admin/routes/zarzadzanie/dokumenty_studentow.py` — `db.session.get(Student)` → `_repo_uzytk.znajdz_po_id`
- `app_admin/routes/zarzadzanie/dziekan.py` — `db.session.get(InternshipEnrollment)` → `_repo_zapisow.znajdz_po_id`; `db.session.query(UploadedDocument)` → `_repo_docs.dokumenty_zapisu`; `CommitteeOutcomeEvaluation.query` → `_repo_ocen.dla_komisji`
- `app_admin/routes/zarzadzanie/firmy.py` — `db.session.add(firma)` → `_repo_firm.zapisz(firma)` (**metoda już istnieje**)
- `app_admin/routes/zarzadzanie/komisja.py` — `db.session.get(InternshipEnrollment)` → `_repo_zapisow.znajdz_po_id`; `LearningOutcome.query` → `_repo_efektow.wszystkie()`; `CommitteeOutcomeEvaluation.query` → `_repo_ocen.dla_komisji`; `db.session.add(CommitteeOutcomeEvaluation)` → `_repo_ocen.zapisz_ocene_komisji`
- `app_admin/routes/zarzadzanie/praktyki.py` — `db.session.get/add/delete(Internship/InternshipEnrollment)` → metody repo (**już istnieją**)
- `app_admin/routes/zarzadzanie/uzytkownicy.py` — `db.session.get/add/delete(User)` → `_repo_uzytk.*` (**metody już istnieją**)
- `app_student/routes/dokumenty.py` — `db.session.get(InternshipEnrollment)` → `_repo_zapisow.znajdz_po_id`
- `app_student/routes/dziennik.py` — `db.session.get(JournalEntry/InternshipEnrollment)`, `add`, `delete` → nowe metody repo
- `app_student/routes/praktyki.py` — wiele `db.session.*` → repo metody (w tym nowe)
- `app_student/routes/pulpit.py` — `db.session.query(ProcessEvent)` → `_repo_zapisow.ostatnie_zdarzenie`
- `app_student/routes/sprawozdania.py` — `db.session.add/get` → repo
- `core/autoryzacja.py` — `db.session.query(User).filter_by(email)` → `RepozytoriumUzytkownikow.znajdz_po_emailu` (**metoda już istnieje**)
- `celery_app.py` — `db.session.get(InternshipEnrollment)` → `RepozytoriumZapisow.znajdz_po_id`

### Uzasadnione wyjątki (zostawić w spokoju)
- `core/uslugi/workflow.py` — `with_for_update()` to pesymistyczny lock transakcyjny, musi być blisko sesji
- `core/uslugi/ocenianie.py` — `db.session.add(ok/sp)` w `zapisz_oceny` — serwis może zarządzać obiektami które tworzy
- `core/uslugi/praktyki.py` — `db.session.add(report/zdarzenie)` — j.w.
- `core/uslugi/dokumenty.py` — `db.session.query(InternshipSchedule/JournalEntry)` w `buduj_kontekst` — to warstwa usług, akceptowalne; do refaktoru w Priorytecie 3

---

## 🟡 PRIORYTET 2 — Reszta bilingwizmu

- Usunąć `@property` shimy `imie`, `nazwisko`, `numer_albumu` z `core/modele/uzytkownicy.py` → zaktualizować callerów w route'ach i szablonach
- Przemianować klasy repozytoriów `RepozytoriumXxx` → `XxxRepository` (9 klas, ~100 miejsc importu) — duże, wymaga globalnego find&replace
- Polskie zmienne w route'ach nadal obecne: `wnioski`, `decyzja`, `komentarz`, `firma` (local var), `efekty` (jako template key), `istniejace`, `opinia`, `charakterystyka`, `opis`, `wiedza`, `dokumenty_list`, `data_od`, `data_do`
- Template context keys: `zapis=enrollment`, `efekty=outcomes` — szablony wciąż dostają polskie nazwy

---

## 🟡 PRIORYTET 3 — Pozostałe boskie metody

| Plik | Metoda | Co wyekstrahować |
|------|--------|-----------------|
| `app_admin/routes/dokumenty.py` | `stream_status` | Pętla SSE z `time.sleep()` → serwis/generator |
| `app_student/routes/dziennik.py` | `nowy_wpis`, `krok3_harmonogram` | Walidacja + tworzenie obiektów → `UslugaDziennika` |
| `app_student/routes/praktyki.py` | `kreator_firma`, `kreator_wniosek` | Zarządzanie `WorkplaceDetails`, `PathJustification` → `UslugaPraktyk` |
| `core/uslugi/dokumenty.py` | `buduj_kontekst` | Drabinka if/elif (10 gałęzi) → strategia/registry per typ dokumentu |
| `core/pliki.py` | cały plik | Rozdzielić: routing, Magic Bytes validation, AES-GCM, HTTP upload |
| `core/autoryzacja.py` | Azure AD flow | Wyekstrahować: OAuth token exchange, user lookup, session setup |
| `celery_app.py` | `generate_pdf_dziennik` | DB fetch → repo; PDF call → serwis; zapis na dysk → osobna funkcja |
| `app_student/routes/dokumenty.py` | `generuj` | Walidacja kompletności + budowanie tablicy ostrzeżeń → serwis |

---

## 🟢 PRIORYTET 4 — Logika w szablonach (Dumb Views)

Każdy z poniższych szablonów wymaga przeniesienia logiki do właściwości modelu lub serwisu:

| Szablon | Problem |
|---------|---------|
| `app_admin/templates/dashboard/index.html` | `item.dni_do_deadline == 0` — kolor ostrzeżenia |
| `app_admin/templates/documents/panel.html` | `status.value == 'COMPLETED'` |
| `app_admin/templates/logi/index.html` | `{% set rola = z.executed_by.rola.value %}` |
| `app_admin/templates/zarzadzanie/dziekan/decyzja.html` | Walidacja blokady zgody dyrektora |
| `app_admin/templates/zarzadzanie/enrollments/list.html` | `border_color = '#3b82f6'` z if/elif po statusach |
| `app_admin/templates/zarzadzanie/komisja/weryfikuj.html` | `<input required>` zależne od stanu ewaluacji |
| `app_admin/templates/evaluation/lista_ocen.html` | `p.final_grade >= 3.0` — kolor oceny |
| `app_admin/templates/zarzadzanie/szczegoly_praktyki.html` | `praktyka.lacznie_godzin / 1.6` (martwy szablon?) |
| `app_student/templates/dziennik/index.html` | `wpisy \| length / 120 * 100 \| int` |
| `app_student/templates/praktyki/lista.html` | `{% set jest_zwrocone = zapis_info.zwrocone %}` + kolory |
| `app_student/templates/dashboard/index.html` | `status.value == 'DIRECTOR_APPROVAL'` |
| `app_student/templates/praktyki/szczegoly_zgloszenia.html` | `employment_subtype == 'INTERNSHIP'` |
| `app_student/templates/dokumenty/panel.html` | `if not item.firma_ma_umowe` |

Rozwiązanie: właściwości `@property` na modelach lub gotowe flagi z serwisu przekazywane do szablonu.

---

## Konwencje projektu

- Język kodu: angielski (zmienne, metody, klasy)
- Język UI i flash messages: polski
- Commit messages: po polsku lub angielsku, opisowe
- Nie używać `db.session` bezpośrednio w route'ach — tylko `db.session.commit()` jest OK
- Nie używać `Model.query.*` — używać `db.session.query()` lub `db.select()` wyłącznie w repozytoriach
- Formularze WTForms mogą mieć polskie nazwy pól (są interfejsem użytkownika)
