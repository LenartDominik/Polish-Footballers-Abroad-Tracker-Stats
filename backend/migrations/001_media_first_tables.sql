-- Migracja 001: tabele media-first MVP (PLAN_MEDIA_FIRST_MVP.md, Sekcje 1-2)
-- Wykonać w Supabase SQL Editor po zatwierdzeniu przez usera:
--   1. Database -> Backups: ręczny backup (punkt 5 checklisty)
--   2. Zaznaczyć CAŁY skrypt i uruchomić naraz (jedna transakcja)
--
-- Zasady (checklista bezpieczeństwa migracji):
--   - Idempotentna: IF NOT EXISTS — ponowne uruchomienie nie robi krzywdy
--   - Same operacje CREATE/ENABLE — nic nie usuwa, nie zmienia istniejących tabel
--   - Plik po wykonaniu na Supabase jest ZAMROŻONY; poprawki tylko w 002_*.sql
--   - RLS włączony bez polityk = anonimowy dostęp zablokowany,
--     backend (service key) działa normalnie (service role omija RLS)

BEGIN;

-- ============================================================
-- 1. player_match_logs — jeden wiersz = jeden występ zawodnika w meczu
-- ============================================================
CREATE TABLE IF NOT EXISTS player_match_logs (
    id                BIGSERIAL PRIMARY KEY,
    player_id         BIGINT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    match_id          INTEGER NOT NULL,               -- RapidAPI event id
    season            VARCHAR(10) NOT NULL,           -- '2026/27'
    match_date        DATE NOT NULL,                  -- UTC
    competition_name  VARCHAR(100) NOT NULL,
    competition_type  VARCHAR(20) NOT NULL,           -- league / european / domestic
    competition_id    INTEGER,
    opponent          VARCHAR(100) NOT NULL,
    is_home           BOOLEAN NOT NULL,
    score             VARCHAR(20),                    -- '2:1' lub NULL
    minutes           INTEGER NOT NULL DEFAULT 0,
    goals             INTEGER NOT NULL DEFAULT 0,
    assists           INTEGER NOT NULL DEFAULT 0,
    yellow_cards      INTEGER NOT NULL DEFAULT 0,
    red_cards         INTEGER NOT NULL DEFAULT 0,
    appearance        VARCHAR(10) NOT NULL,           -- start / sub / bench
    rating            NUMERIC(4,2),
    created_at        TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_match_log_player_match UNIQUE (player_id, match_id),
    CONSTRAINT ck_match_log_appearance CHECK (appearance IN ('start', 'sub', 'bench')),
    CONSTRAINT ck_match_log_comp_type CHECK (competition_type IN ('league', 'european', 'domestic'))
);

-- Profil zawodnika i forma: ostatnie mecze danego gracza
CREATE INDEX IF NOT EXISTS idx_match_logs_player_date
    ON player_match_logs (player_id, match_date DESC);
-- Raport tygodnia: mecze w przedziale dat
CREATE INDEX IF NOT EXISTS idx_match_logs_date
    ON player_match_logs (match_date);
-- Przełącznik sezonów
CREATE INDEX IF NOT EXISTS idx_match_logs_season
    ON player_match_logs (season);

-- ============================================================
-- 2. weekly_reports — raport tygodnia (draft -> published)
-- ============================================================
CREATE TABLE IF NOT EXISTS weekly_reports (
    id                BIGSERIAL PRIMARY KEY,
    season            VARCHAR(10) NOT NULL,
    period_start      DATE NOT NULL,
    period_end        DATE NOT NULL,
    title             VARCHAR(200) NOT NULL,
    editorial_comment TEXT,
    status            VARCHAR(20) NOT NULL DEFAULT 'draft',
    generated_at      TIMESTAMP NOT NULL DEFAULT now(),
    published_at      TIMESTAMP,
    CONSTRAINT uq_report_period UNIQUE (period_start, period_end),
    CONSTRAINT ck_report_status CHECK (status IN ('draft', 'published')),
    CONSTRAINT ck_report_dates CHECK (period_end >= period_start)
);

CREATE INDEX IF NOT EXISTS idx_reports_season ON weekly_reports (season);
-- Archiwum / latest: szybkie wyszukiwanie po statusie
CREATE INDEX IF NOT EXISTS idx_reports_status
    ON weekly_reports (status, period_start DESC);

-- ============================================================
-- 3. RLS: włączony, brak polityk = dostęp anonimowy zablokowany
--    (backend na service key działa bez zmian)
-- ============================================================
ALTER TABLE player_match_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_reports ENABLE ROW LEVEL SECURITY;

COMMIT;
