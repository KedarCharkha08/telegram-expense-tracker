-- Telegram Expense Tracker — Supabase schema
-- Run this whole file once in Supabase → SQL Editor → New query → Run.

create extension if not exists "pgcrypto";

create table if not exists public.expenses (
    id           uuid primary key default gen_random_uuid(),
    created_at   timestamptz  not null default now(),

    amount       numeric(12,2) not null check (amount > 0),
    category     varchar(48)   not null default 'Uncategorized',
    description  text          not null default '',
    spent_on     date          not null default (now() at time zone 'Asia/Kolkata')::date,

    -- provenance / audit
    raw_message  text          not null,
    tg_user_id   bigint,
    tg_chat_id   bigint,

    -- Telegram retries failed deliveries; this makes re-delivery a no-op
    -- instead of a duplicate expense.
    update_id    bigint unique,

    deleted_at   timestamptz   -- soft delete, powers /undo
);

-- Dashboard reads: recent-first, and per-category rollups by month.
create index if not exists expenses_spent_on_idx  on public.expenses (spent_on desc);
create index if not exists expenses_category_idx  on public.expenses (category);
create index if not exists expenses_tg_user_idx   on public.expenses (tg_user_id);
create index if not exists expenses_live_idx      on public.expenses (spent_on desc)
    where deleted_at is null;

-- Convenience view: only live rows, newest first. The dashboard reads this.
-- security_invoker makes the view respect the *caller's* RLS instead of the
-- owner's. Without it Supabase's linter flags this as a SECURITY DEFINER view
-- that quietly bypasses the policy below. (Needs Postgres 15+; every Supabase
-- project created in the last couple of years qualifies.)
create or replace view public.expenses_live
    with (security_invoker = on) as
    select id, created_at, spent_on, amount, category, description,
           raw_message, tg_user_id
    from public.expenses
    where deleted_at is null
    order by spent_on desc, created_at desc;

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- The backend uses the service_role key, which bypasses RLS entirely.
-- The dashboard uses the anon key, which needs an explicit read policy.
-- Without this, the anon key can read nothing — which is the safe default.
-- ---------------------------------------------------------------------------
alter table public.expenses enable row level security;

drop policy if exists "anon can read expenses" on public.expenses;
create policy "anon can read expenses"
    on public.expenses
    for select
    to anon
    using (deleted_at is null);

-- No insert/update/delete policy for anon: the dashboard is read-only.
-- Writes only ever happen through the backend's service_role key.
