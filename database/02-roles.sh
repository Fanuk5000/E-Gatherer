#!/bin/sh
set -e

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v db_name="$POSTGRES_DB" \
    -v etl_user="${ETL_WORKER_USER:-etl_worker}" \
    -v etl_pass="${ETL_WORKER_PASSWORD:?ETL_WORKER_PASSWORD must be set}" \
    -v grafana_user="${GRAFANA_READER_USER:-grafana_reader}" \
    -v grafana_pass="${GRAFANA_READER_PASSWORD:?GRAFANA_READER_PASSWORD must be set}" <<-'EOSQL'

-- 1. Create least-privilege roles idempotently
SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'etl_user', :'etl_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'etl_user') \gexec

SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'grafana_user', :'grafana_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'grafana_user') \gexec

-- 2. Harden public schema (extensions remain usable, no arbitrary table creation)
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- 3. Create domain-separated schemas owned by etl_worker
SELECT format('CREATE SCHEMA IF NOT EXISTS catalog AUTHORIZATION %I', :'etl_user') \gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS pricing AUTHORIZATION %I', :'etl_user') \gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS etl AUTHORIZATION %I', :'etl_user') \gexec
SELECT format('CREATE SCHEMA IF NOT EXISTS analytics AUTHORIZATION %I', :'etl_user') \gexec

-- 4. Grant database connect and configure default search_path
SELECT format('GRANT CONNECT ON DATABASE %I TO %I, %I', :'db_name', :'etl_user', :'grafana_user') \gexec
SELECT format('ALTER ROLE %I SET search_path TO catalog, pricing, etl, analytics, public', :'etl_user') \gexec
SELECT format('ALTER ROLE %I SET search_path TO analytics, public', :'grafana_user') \gexec

-- 5. Grant grafana_reader read-only access strictly to analytics schema
SELECT format('GRANT USAGE ON SCHEMA analytics TO %I', :'grafana_user') \gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO %I', :'grafana_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA analytics GRANT SELECT ON TABLES TO %I', :'etl_user', :'grafana_user') \gexec

EOSQL
