-- AirRev Engine — Supabase Schema
-- Run these in your Supabase SQL Editor

-- ─────────────────────────────────────────
-- 1. Listing Analytics (search logs)
-- ─────────────────────────────────────────
create table if not exists listing_analytics (
  id              uuid default gen_random_uuid() primary key,
  mls_number      text not null,
  analysis_type   text not null,
  community       text,
  purchase_price  numeric,
  cap_rate_ltr    numeric,
  cap_rate_str    numeric,
  coc_ltr         numeric,
  coc_str         numeric,
  recommendation  text,
  best_strategy   text,
  user_id         uuid references auth.users(id),
  created_at      timestamptz default now()
);

-- Index for fast lookups
create index on listing_analytics(mls_number);
create index on listing_analytics(community);
create index on listing_analytics(created_at desc);

-- RLS: Only service role can write, authenticated users can read their own
alter table listing_analytics enable row level security;

create policy "Service role full access"
  on listing_analytics for all
  using (auth.role() = 'service_role');

create policy "Users read own records"
  on listing_analytics for select
  using (auth.uid() = user_id);


-- ─────────────────────────────────────────
-- 2. Community Insights (170+ Calgary communities)
-- ─────────────────────────────────────────
create table if not exists community_insights (
  id                        uuid default gen_random_uuid() primary key,
  community_name            text not null unique,
  city                      text default 'Calgary',
  overview                  text,

  -- LTR rent by bedroom (JSONB: {"0": 1650, "1": 1950, "2": 2800})
  ltr_avg_rent_by_bedroom   jsonb default '{}',

  -- STR nightly by bedroom
  str_avg_nightly_by_bedroom jsonb default '{}',

  str_avg_occupancy         numeric default 0.68,
  avg_cap_rate_ltr          numeric default 0.042,
  avg_cap_rate_str          numeric default 0.055,
  active_listings           integer default 0,
  avg_days_on_market        integer default 28,
  median_sale_price         numeric,
  price_per_sqft            numeric,
  yoy_appreciation          numeric default 0.06,
  walkability_score         integer,
  transit_score             integer,

  updated_at                timestamptz default now()
);

create index on community_insights(community_name);

alter table community_insights enable row level security;

create policy "Public read"
  on community_insights for select
  using (true);

create policy "Service role write"
  on community_insights for all
  using (auth.role() = 'service_role');


-- ─────────────────────────────────────────
-- 3. Report Cache (avoid re-running analysis)
-- ─────────────────────────────────────────
create table if not exists report_cache (
  id          uuid default gen_random_uuid() primary key,
  mls_number  text not null,
  report_type text not null,
  report_data jsonb not null,
  created_at  timestamptz default now(),
  expires_at  timestamptz default (now() + interval '24 hours'),
  unique(mls_number, report_type)
);

create index on report_cache(mls_number, report_type);

-- Auto-delete expired cache
create or replace function delete_expired_cache()
returns void language sql as $$
  delete from report_cache where expires_at < now();
$$;


-- ─────────────────────────────────────────
-- 5. CREB Monthly Reports
-- ─────────────────────────────────────────
create table if not exists creb_monthly_reports (
  id           uuid default gen_random_uuid() primary key,
  report_month integer not null,
  report_year  integer not null,
  community    text not null default 'Calgary',
  report_data  jsonb not null,
  updated_at   timestamptz default now(),
  unique(report_month, report_year, community)
);

create index on creb_monthly_reports(report_year, report_month);

alter table creb_monthly_reports enable row level security;

create policy "Public read CREB reports"
  on creb_monthly_reports for select using (true);

create policy "Service role write CREB reports"
  on creb_monthly_reports for all
  using (auth.role() = 'service_role');
-- ─────────────────────────────────────────
insert into community_insights (community_name, ltr_avg_rent_by_bedroom, str_avg_nightly_by_bedroom, median_sale_price, price_per_sqft)
values
  ('Beltline',        '{"0":1650,"1":1950,"2":2800,"3":3700}', '{"0":115,"1":136,"2":196,"3":259}', 420000, 485),
  ('Mission',         '{"0":1550,"1":1900,"2":2650,"3":3450}', '{"0":108,"1":133,"2":185,"3":241}', 480000, 510),
  ('Inglewood',       '{"0":1450,"1":1800,"2":2450,"3":3200}', '{"0":101,"1":126,"2":171,"3":224}', 510000, 430),
  ('Bridgeland',      '{"0":1500,"1":1850,"2":2550,"3":3300}', '{"0":105,"1":129,"2":178,"3":231}', 495000, 445),
  ('Mahogany',        '{"1":2100,"2":2700,"3":3400,"4":4000}', '{"1":147,"2":189,"3":238,"4":280}', 680000, 380),
  ('Evanston',        '{"1":1950,"2":2550,"3":3200,"4":3900}', '{"1":136,"2":178,"3":224,"4":273}', 620000, 355)
on conflict (community_name) do nothing;
