# PostgreSQL 17 Database Service

Standalone Docker Compose service for local development and production database hosting.

---

## Quick Start

### 1. Navigate to directory

```bash
cd database
```

### 2. Verify `.env` file

Ensure `.env` exists (copied from `.env.example` if needed):

```bash
cp ---update=none .env.example .env
```

### 3. Start Database

```bash
docker compose up -d
```

### 4. Check Container Status & Health

```bash
docker compose ps
```

Wait until status shows `healthy` (takes ~5–10 seconds).

---

## Database Management & Inspection

### View Live Logs

```bash
docker compose logs -f
```

### Interactive `psql` Shell

Connect directly to the database inside the container:

```bash
docker exec -it postgres_db psql -U postgres -d egatherer
```

Inside `psql`:

- Check installed extensions: `\dx`
- List tables: `\dt`
- List analytical views: `\dv`
- Exit shell: `\q`

---

## Stopping & Teardown

### Stop Service (preserves data)

```bash
docker compose down
```

### Full Reset (deletes data volume & starts fresh)

```bash
docker compose down -v
```
