# PostgreSQL 17 Database Service

Standalone Docker Compose service for local development and production database hosting.

---

## Quick Start

### 1. Navigate to directory

```bash
cd database
```

### 2. Verify `.env` file

Ensure `.env` exists (copied from `.env.example` if needed) and set passwords for `ETL_WORKER_PASSWORD` and `GRAFANA_READER_PASSWORD`:

```bash
cp --update=none .env.example .env
```

### 3. Pre-flight check for `02-roles.sh`

Ensure POSIX shell script has execute permission and valid syntax for `postgres:17-alpine` (`/bin/sh`):

```bash
chmod +x 02-roles.sh
sh -n 02-roles.sh
```

*(Zero output with exit code `0` means syntax is valid.)*

### 4. Start Database

```bash
docker compose up -d
```

### 5. Check Container Status & Health

```bash
docker compose ps
```

Wait until status shows `healthy` (takes ~5–10 seconds).

---

## Bootstrap Schemas & Tables (`etl_worker`)

Run from the **project root** after loading `database/.env` into the shell so Python connects as `etl_worker` (non-superuser):

```bash
set -a && source database/.env && set +a
python3 -m src.main
```

- `set -a` enables auto-export (`allexport`), so variables read by `source database/.env` are inherited by child processes (`python3 -m src.main` / `os.getenv(...)`).
- `set +a` disables auto-export afterward so later shell variables stay local.

---

## Database Management & Inspection

### View Live Logs

```bash
cd database && docker compose logs -f
```

### Interactive `psql` Shell

Load `.env` and connect inside the container:

```bash
source database/.env
docker exec -it postgres_db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Inside `psql`, inspect the domain-split structure:

- Installed extensions (`pg_trgm`): `\dx`
- Roles (`etl_worker`, `grafana_reader`): `\du`
- Schemas & owners (`catalog`, `pricing`, `etl`, `analytics`, `public`): `\dn+`
- Catalog tables: `\dt catalog.*`
- Pricing tables: `\dt pricing.*`
- ETL log tables: `\dt etl.*`
- Analytical views: `\dv analytics.*`
- Exit shell: `\q`

---

## Verification & Role Isolation Tests

Load `.env` first (`source database/.env`), then run quick checks:

### 1. Verify `etl_worker` owns schemas & sees tables/views

```bash
docker exec -it postgres_db psql -U "$ETL_WORKER_USER" -d "$POSTGRES_DB" \
  -c "\dn+" \
  -c "\dt catalog.*" \
  -c "\dt pricing.*" \
  -c "\dt etl.*" \
  -c "\dv analytics.*"
```

### 2. Verify `grafana_reader` least-privilege isolation

Should **succeed** (read-only access to `analytics`):

```bash
docker exec -it postgres_db psql -U "$GRAFANA_READER_USER" -d "$POSTGRES_DB" \
  -c "SELECT * FROM analytics.v_daily_price_aggregates LIMIT 1;"
```

Should **fail** with `permission denied` (raw tables isolated):

```bash
docker exec -it postgres_db psql -U "$GRAFANA_READER_USER" -d "$POSTGRES_DB" \
  -c "SELECT * FROM pricing.price_history LIMIT 1;"
```

---

## Inspecting Scraped Data & Analytical Views

After running `make scrape-save` (or `uv run python -m src.collectors.websites.webscraper_io --save`), inspect stored records via `psql`:

```sql
-- Latest scraper runs
SELECT id, scraper_name, status, items_scraped, started_at, finished_at
FROM etl.scrape_logs
ORDER BY id DESC
LIMIT 5;

-- Scraped products with store links and latest prices
SELECT p.id, p.brand, p.model_name, sp.external_id, ph.price_uah, ph.price_usd_computed, ph.recorded_at
FROM catalog.products p
JOIN catalog.store_products sp ON sp.product_id = p.id
JOIN pricing.price_history ph ON ph.store_product_id = sp.id
ORDER BY ph.recorded_at DESC
LIMIT 10;

-- Analytical and matching views
SELECT * FROM analytics.v_daily_price_aggregates LIMIT 10;
SELECT * FROM analytics.v_product_match_bare_sql LIMIT 10;
SELECT * FROM analytics.v_product_match_trgm LIMIT 10;
```

Run bare SQL (`ILIKE` / `LIKE`) vs `pg_trgm` (`EXPLAIN (ANALYZE, BUFFERS)`) benchmark from project root:

```bash
uv run python -m scripts.benchmark_trgm --queries Mercedes Mercdes Ferari Toyta
```

---

## Stopping & Teardown

### Stop Service (preserves data)

```bash
docker compose down
```

### Full Reset (deletes data volume & re-runs `01-init.sql` + `02-roles.sh`)

```bash
docker compose down -v
```
