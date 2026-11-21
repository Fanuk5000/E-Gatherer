"""Large-scale (100k+ rows) benchmark comparing bare SQL (B-Tree/Seq Scan) vs pg_trgm (GIN)."""

import argparse
import asyncio
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.benchmark_trgm import _explain
from src.db.connection import close_db, get_session


async def _prepare_temp_tables(session: AsyncSession, rows: int) -> None:
    """Creates isolated TEMP tables (bare B-Tree vs pg_trgm GIN) with synthetic catalog data."""
    t0 = time.perf_counter()
    await session.execute(
        text(
            """
            CREATE TEMP TABLE bench_bare (
                id integer PRIMARY KEY,
                model_name varchar(255) NOT NULL
            ) ON COMMIT DROP
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TEMP TABLE bench_trgm (
                id integer PRIMARY KEY,
                model_name varchar(255) NOT NULL
            ) ON COMMIT DROP
            """
        )
    )

    # Low selectivity (~0.1% per target brand) mimics real multi-brand catalogs so GIN index triggers.
    insert_sql = """
        INSERT INTO bench_bare (id, model_name)
        SELECT
            g,
            CASE
                WHEN g % 1000 = 0 THEN 'Mercedes-Benz W123 280E ' || (1955 + (g % 40))::text
                WHEN g % 1000 = 1 THEN 'Ferrari F40 Competizione ' || (1984 + (g % 15))::text
                WHEN g % 1000 = 2 THEN 'GeForce RTX4070Ti Super ' || (g % 50)::text || 'GB'
                ELSE 'Brand' || (g % 250)::text || ' Model-' || (g % 800)::text || ' ' || substr(md5(g::text), 1, 8)
            END
        FROM generate_series(1, :rows) AS g
    """
    await session.execute(text(insert_sql), {"rows": rows})
    await session.execute(text("INSERT INTO bench_trgm SELECT * FROM bench_bare"))

    await session.execute(
        text("CREATE INDEX ix_bench_bare_btree ON bench_bare (model_name)")
    )
    await session.execute(
        text(
            "CREATE INDEX ix_bench_trgm_gin ON bench_trgm USING gin (model_name gin_trgm_ops)"
        )
    )
    await session.execute(text("ANALYZE bench_bare"))
    await session.execute(text("ANALYZE bench_trgm"))
    prep_ms = (time.perf_counter() - t0) * 1000
    print(
        f"Prepared {rows:,} synthetic rows in bare (B-Tree) & trgm (GIN) temp tables in {prep_ms:.1f} ms"
    )


async def _run_large_benchmark(
    rows: int, queries: list[str], similarity_limit: float
) -> None:
    async with get_session() as session:
        await _prepare_temp_tables(session, rows)
        await session.execute(
            text("SELECT set_limit(:threshold)"),
            {"threshold": similarity_limit},
        )

        for query in queries:
            print(f"\n--- Query ({rows:,} rows): {query!r} ---")
            await _explain(
                session,
                f"Bare SQL ILIKE ({query!r})",
                "SELECT id, model_name FROM bench_bare WHERE model_name ILIKE :pat LIMIT 20",
                {"pat": f"%{query}%"},
            )
            await _explain(
                session,
                f"Same-task ILIKE + GIN ({query!r})",
                "SELECT id, model_name FROM bench_trgm WHERE model_name ILIKE :pat LIMIT 20",
                {"pat": f"%{query}%"},
            )
            await _explain(
                session,
                f"Fuzzy pg_trgm % + GIN ({query!r})",
                "SELECT id, model_name, similarity(model_name, :q) AS s "
                "FROM bench_trgm WHERE model_name % :q ORDER BY s DESC LIMIT 20",
                {"q": query},
            )

        # Batch match: 25 noisy incoming listings matched against N-row catalog
        batch_values = ", ".join(
            f"('Mercdes-Benz W123 {1955 + i}')"
            if i % 2 == 0
            else f"('Ferari F40 {1984 + (i % 15)}')"
            for i in range(25)
        )
        await _explain(
            session,
            f"Batch match (25 incoming vs {rows:,} rows) — Bare SQL ILIKE",
            f"""
            WITH incoming(title) AS (VALUES {batch_values})
            SELECT i.title, b.model_name
            FROM incoming i
            JOIN bench_bare b ON b.model_name ILIKE '%' || i.title || '%'
            LIMIT 50
            """,
        )
        await _explain(
            session,
            f"Batch match (25 incoming vs {rows:,} rows) — pg_trgm % + GIN",
            f"""
            WITH incoming(title) AS (VALUES {batch_values})
            SELECT i.title, t.model_name, similarity(t.model_name, i.title) AS s
            FROM incoming i
            JOIN bench_trgm t ON t.model_name % i.title
            ORDER BY s DESC
            LIMIT 50
            """,
        )


async def _main(rows: int, queries: list[str], similarity_limit: float) -> None:
    try:
        await _run_large_benchmark(rows, queries, similarity_limit)
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Benchmark bare SQL ILIKE vs pg_trgm GIN index on large synthetic dataset."
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=100_000,
        help="Number of synthetic rows to generate in TEMP tables (default: 100000).",
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        default=["Mercedes", "Mercdes", "Ferari", "RTX4070Ti"],
        help="Search strings (exact + typos) to compare.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.2,
        help="pg_trgm similarity threshold for percent operator.",
    )
    args = parser.parse_args()
    asyncio.run(
        _main(rows=args.rows, queries=args.queries, similarity_limit=args.threshold)
    )
