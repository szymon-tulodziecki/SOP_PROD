-- Migration: add commission members to examinations table
ALTER TABLE examinations
    ADD COLUMN IF NOT EXISTS commission_chair    VARCHAR(200),
    ADD COLUMN IF NOT EXISTS commission_member_2 VARCHAR(200),
    ADD COLUMN IF NOT EXISTS commission_member_3 VARCHAR(200);
