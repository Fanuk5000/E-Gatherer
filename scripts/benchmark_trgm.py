"""Benchmark comparing bare SQL (ILIKE / LIKE) vs pg_trgm (GIN trigram) queries and views."""

import argparse
import asyncio
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import close_db, get_session, init_db
from src.db.repository import DatabaseRepository


async def _explain(
    session: AsyncSession,
    label: str,
    sql: str,
    params: dict[str, Any] | None = None,
) -> None:
    """Runs EXPLAIN (ANALYZE, BUFFERS) and prints plan and wall-clock time."""
    started = time.perf_counter()
    result = await session.execute(
        text(f"EXPLAIN (ANALYZE, BUFFERS) {sql}"), params or {}
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    plan_lines = [row[0] for row in result.all()]

    print(f"\n=== {label} ({elapsed_ms:.2f} ms client) ===")
    for line in plan_lines:
        print(f"  {line}")


async def _run_benchmark(queries: list[str], similarity_limit: float) -> None:
    await init_db()
    try:
        async with get_session() as session:
            repo = DatabaseRepository(session)
            total_products = (
                await session.execute(text("SELECT COUNT(*) FROM catalog.products"))
            ).scalar_one()
            print(f"Products in catalog.products: {total_products}")

            for query in queries:
                print(f"\n--- Query: {query!r} ---")

                t0 = time.perf_counter()
                bare_hits = await repo.search_products_bare_sql(query)
                bare_ms = (time.perf_counter() - t0) * 1000

                t1 = time.perf_counter()
                trgm_hits = await repo.search_products_trgm(
                    query, min_similarity=similarity_limit
                )
                trgm_ms = (time.perf_counter() - t1) * 1000

                print(f"Bare SQL ILIKE : {len(bare_hits)} hit(s) in {bare_ms:.2f} ms")
                for p in bare_hits[:5]:
                    print(f"    [bare] {p.model_name}")

                print(
                    f"pg_trgm (% >= {similarity_limit}): {len(trgm_hits)} hit(s) in {trgm_ms:.2f} ms"
                )
                for p, score in trgm_hits[:5]:
                    print(f"    [trgm {score:.3f}] {p.model_name}")

                await _explain(
                    session,
                    f"EXPLAIN bare SQL ILIKE ({query!r})",
                    "SELECT id, model_name FROM catalog.products WHERE model_name ILIKE :pat LIMIT 20",
                    {"pat": f"%{query}%"},
                )
                await session.execute(
                    text("SELECT set_limit(:threshold)"),
                    {"threshold": similarity_limit},
                )
                await _explain(
                    session,
                    f"EXPLAIN pg_trgm % ({query!r})",
                    "SELECT id, model_name, similarity(model_name, :q) AS s "
                    "FROM catalog.products WHERE model_name % :q ORDER BY s DESC LIMIT 20",
                    {"q": query},
                )

            await _explain(
                session,
                "View: analytics.v_product_match_bare_sql",
                "SELECT * FROM analytics.v_product_match_bare_sql LIMIT 50",
            )
            await _explain(
                session,
                "View: analytics.v_product_match_trgm",
                "SELECT * FROM analytics.v_product_match_trgm LIMIT 50",
            )
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare bare SQL ILIKE/LIKE vs pg_trgm queries and views."
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        default=["Asus", "Asuss", "Lenvo", "ThinkPd"],
        help="Search strings (exact + typos) to compare.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.2,
        help="pg_trgm similarity threshold for percent operator.",
    )
    args = parser.parse_args()
    asyncio.run(_run_benchmark(queries=args.queries, similarity_limit=args.threshold))
