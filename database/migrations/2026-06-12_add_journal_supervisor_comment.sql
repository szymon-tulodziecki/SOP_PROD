-- Komentarz opiekuna praktyki (UOPZ) przy pojedynczym wpisie dziennika.
-- Uruchomienie na działającym serwerze:
--   docker exec -i sop_db psql -U ans_admin -d ans_praktyki < database/migrations/2026-06-12_add_journal_supervisor_comment.sql

ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS supervisor_comment TEXT;
