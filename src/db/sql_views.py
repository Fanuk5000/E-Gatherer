"""SQL definitions for PostgreSQL analytical views queried by Grafana."""

CREATE_V_DAILY_PRICE_AGGREGATES = """
CREATE OR REPLACE VIEW v_daily_price_aggregates AS
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
FROM price_history ph
JOIN store_products sp ON sp.id = ph.store_product_id
JOIN products p ON p.id = sp.product_id
JOIN categories c ON c.id = p.category_id
GROUP BY
    p.id,
    p.brand,
    p.model_name,
    c.name,
    DATE(ph.recorded_at);
"""

CREATE_V_PRICE_GROWTH = """
CREATE OR REPLACE VIEW v_price_growth AS
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
FROM v_daily_price_aggregates;
"""

ANALYTICAL_VIEWS_DDL = [
    CREATE_V_DAILY_PRICE_AGGREGATES,
    CREATE_V_PRICE_GROWTH,
]
