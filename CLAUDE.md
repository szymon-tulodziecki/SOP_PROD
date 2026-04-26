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
| 11 | **Priorytet 1 — db.session w route'ach**: wszystkie nowe metody repo dodane (`znajdz_po_id`, `usun`, `znajdz_odrzucony`, `usun_zdarzenia_zapisu`, `zapisz_harmonogram`, `ostatnie_zdarzenie`, `aktywni_mentorzy`, `dla_komisji`, `zapisz_ocene_komisji`, `wszystkie_zdarzenia`, `dokumenty_zapisu`, `zapisz_log`); wszystkie route'y zaktualizowane |
| 12 | **Priorytet 2 — bilingwizm**: usunięto polskie `@property` shimy (`imie/nazwisko/numer_albumu` i pochodne) z `uzytkownicy.py`; zaktualizowano 12 szablonów HTML i 32 pliki Python; przemianowano 9 klas repozytoriów `RepozytoriumXxx → XxxRepository` |
| 13 | **Priorytet 4 — Dumb Views**: przeniesiono całą logikę z 11 szablonów do `@property` na modelach (`status_css_class`, `status_label`, `is_pending`, `is_in_progress`, `firma_ma_umowe`, `moze_pobrac_wydruki`, `final_grade_is_passing`, itd.) i serwisów (`deadline_is_today`, `entries_progress_percent`); usunięto martwy `dokumenty/panel.html` |

---

## ✅ Uzasadnione wyjątki (zostawić w spokoju)

- `core/uslugi/workflow.py` — `with_for_update()` to pesymistyczny lock transakcyjny, musi być blisko sesji
- `core/uslugi/ocenianie.py` — `db.session.add(ok/sp)` w `zapisz_oceny` — serwis może zarządzać obiektami które tworzy
- `core/uslugi/praktyki.py` — `db.session.add(report/zdarzenie)` — j.w.
- `app_student/routes/praktyki.py` `kreator_firma/kreator_wniosek` — `db.session.add(dm/uz)` dla `WorkplaceDetails`/`PathJustification` bez własnych repo — akceptowalne
- `app_student/routes/sprawozdania.py` — `db.session.add(nowe_spr)` dla `InternshipReport` bez repo

---

## 🟡 PRIORYTET 3 — Pozostałe boskie metody

| Plik | Metoda | Co wyekstrahować | Status |
|------|--------|-----------------|--------|
| `app_admin/routes/dokumenty.py` | `stream_status` | Pętla SSE z `time.sleep()` → generator w serwisie | ❌ |
| `core/uslugi/dokumenty.py` | `buduj_kontekst` | Drabinka if/elif (10 gałęzi) → strategia/registry per typ dokumentu | ❌ |
| `core/pliki.py` | cały plik | Rozdzielić: routing, Magic Bytes validation, AES-GCM, HTTP upload | ❌ |
| `app_student/routes/dokumenty.py` | `generuj` | Walidacja kompletności + budowanie tablicy ostrzeżeń → serwis | ❌ |

---

## Konwencje projektu

- Język kodu: angielski (zmienne, metody, klasy)
- Język UI i flash messages: polski
- Commit messages: po polsku lub angielsku, opisowe
- Nie używać `db.session` bezpośrednio w route'ach — tylko `db.session.commit()` jest OK
- Nie używać `Model.query.*` — używać `db.session.query()` lub `db.select()` wyłącznie w repozytoriach
- Formularze WTForms mogą mieć polskie nazwy pól (są interfejsem użytkownika)
- Klasy repozytoriów: angielska konwencja `XxxRepository` (nie `RepozytoriumXxx`)
