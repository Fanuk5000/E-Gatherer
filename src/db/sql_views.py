"""SQL definitions for PostgreSQL analytical views queried by Grafana."""

CREATE_V_DAILY_PRICE_AGGREGATES = """
CREATE OR REPLACE VIEW analytics.v_daily_price_aggregates AS
SELECT
    p.id AS product_id,
    p.brand,
    p.model_name,
    c.name AS category_name,
    DATE(ph.recorded_at) AS day,
    ROUND(MIN(ph.price_uah), 2) AS min_price_uah,
    ROUND(AVG(ph.price_uah), 2) AS avg_price_uah,
    ROUND(MAX(ph.price_uah), 2) AS max_price_uah,
    ROUND(
        (percentile_cont(0.5) WITHIN GROUP (ORDER BY ph.price_uah))::numeric,
        2
    ) AS median_price_uah,
    ROUND(AVG(ph.price_usd_computed), 2) AS avg_price_usd,
    COUNT(DISTINCT sp.store_id) AS active_stores_count,
    COUNT(ph.id) AS data_points_count
FROM pricing.price_history ph
JOIN catalog.store_products sp ON sp.id = ph.store_product_id
JOIN catalog.products p ON p.id = sp.product_id
JOIN catalog.categories c ON c.id = p.category_id
GROUP BY
    p.id,
    p.brand,
    p.model_name,
    c.name,
    DATE(ph.recorded_at);
"""

CREATE_V_PRICE_GROWTH = """
CREATE OR REPLACE VIEW analytics.v_price_growth AS
SELECT
    product_id,
    brand,
    model_name,
    category_name,
    day,
    median_price_uah,
    LAG(median_price_uah, 1) OVER (
        PARTITION BY product_id ORDER BY day
    ) AS prev_day_median_price,
    ROUND(
        (
            (median_price_uah - LAG(median_price_uah, 1) OVER (PARTITION BY product_id ORDER BY day))
            / NULLIF(LAG(median_price_uah, 1) OVER (PARTITION BY product_id ORDER BY day), 0)
        ) * 100,
        2
    ) AS daily_change_percent
FROM analytics.v_daily_price_aggregates;
"""

CREATE_V_PRODUCT_MATCH_BARE_SQL = """
CREATE OR REPLACE VIEW analytics.v_product_match_bare_sql AS
SELECT
    a.id AS source_product_id,
    a.model_name AS source_model_name,
    b.id AS matched_product_id,
    b.model_name AS matched_model_name
FROM catalog.products a
JOIN catalog.products b
    ON a.id < b.id
   AND (
       LOWER(a.model_name) LIKE '%' || LOWER(NULLIF(SPLIT_PART(b.model_name, ' ', 1), '')) || '%'
       OR LOWER(b.model_name) LIKE '%' || LOWER(NULLIF(SPLIT_PART(a.model_name, ' ', 1), '')) || '%'
   );
"""

CREATE_V_PRODUCT_MATCH_TRGM = """
CREATE OR REPLACE VIEW analytics.v_product_match_trgm AS
SELECT
    a.id AS source_product_id,
    a.model_name AS source_model_name,
    b.id AS matched_product_id,
    b.model_name AS matched_model_name,
    ROUND(similarity(a.model_name, b.model_name)::numeric, 3) AS trgm_similarity,
    ROUND(word_similarity(a.model_name, b.model_name)::numeric, 3) AS trgm_word_similarity
FROM catalog.products a
JOIN catalog.products b
    ON a.id < b.id
   AND a.model_name % b.model_name
ORDER BY trgm_similarity DESC;
"""

CREATE_V_SCRAPE_LOGS = """
CREATE OR REPLACE VIEW analytics.v_scrape_logs AS
SELECT
    id,
    scraper_name,
    status,
    items_scraped,
    error_message,
    started_at,
    finished_at,
    ROUND(EXTRACT(EPOCH FROM (finished_at - started_at))::numeric, 2) AS duration_seconds
FROM etl.scrape_logs;
"""

CREATE_V_EXCHANGE_RATES = """
CREATE OR REPLACE VIEW analytics.v_exchange_rates AS
SELECT
    id,
    currency_code,
    rate_to_uah,
    exchange_date,
    recorded_at
FROM pricing.exchange_rates;
"""

ANALYTICAL_VIEWS_DDL: tuple[str, ...] = (
    CREATE_V_DAILY_PRICE_AGGREGATES,
    CREATE_V_PRICE_GROWTH,
    CREATE_V_PRODUCT_MATCH_BARE_SQL,
    CREATE_V_PRODUCT_MATCH_TRGM,
    CREATE_V_SCRAPE_LOGS,
    CREATE_V_EXCHANGE_RATES,
)
