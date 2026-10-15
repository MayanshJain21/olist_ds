-- ==============================================================================
-- Script: 06_views.sql
-- Description: Creates business analytics views on top of the Star Schema.
-- Views: vw_monthly_revenue, vw_seller_performance, vw_delivery_performance.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. View: Monthly Revenue & Order Metrics (dw.vw_monthly_revenue)
-- ------------------------------------------------------------------------------
CREATE OR ALTER VIEW dw.vw_monthly_revenue AS
SELECT
    d.year,
    d.month,
    d.month_name,
    (d.year * 100) + d.month AS year_month_key,
    COUNT(DISTINCT fs.order_id) AS total_orders,
    COUNT(fs.order_item_id) AS total_items_sold,
    SUM(fs.price) AS total_product_revenue,
    SUM(fs.freight_value) AS total_freight_value,
    SUM(fs.total_value) AS gross_revenue,
    ROUND(AVG(fs.price), 2) AS avg_item_price,
    ROUND(SUM(fs.total_value) / NULLIF(COUNT(DISTINCT fs.order_id), 0), 2) AS avg_order_value
FROM dw.fact_sales fs
INNER JOIN dw.dim_date d
    ON fs.purchase_date_key = d.date_key
WHERE fs.order_status <> 'canceled'
GROUP BY
    d.year,
    d.month,
    d.month_name,
    (d.year * 100) + d.month;
GO

PRINT 'View [dw.vw_monthly_revenue] created.';
GO

-- ------------------------------------------------------------------------------
-- 2. View: Seller Performance & Fulfillment KPI (dw.vw_seller_performance)
-- ------------------------------------------------------------------------------
CREATE OR ALTER VIEW dw.vw_seller_performance AS
SELECT
    s.seller_id,
    s.city AS seller_city,
    s.state AS seller_state,
    COUNT(DISTINCT fs.order_id) AS total_orders,
    COUNT(fs.order_item_id) AS total_units_sold,
    SUM(fs.total_value) AS total_gross_revenue,
    ROUND(AVG(CAST(fs.review_score AS FLOAT)), 2) AS avg_review_score,
    ROUND(AVG(fs.delivery_days), 2) AS avg_delivery_days,
    ROUND(AVG(fs.delay_days), 2) AS avg_delay_days,
    SUM(CASE WHEN fs.delay_days > 0 THEN 1 ELSE 0 END) AS delayed_orders_count,
    ROUND(
        SUM(CASE WHEN fs.delay_days <= 0 THEN 1.0 ELSE 0.0 END) * 100.0 / NULLIF(COUNT(fs.delay_days), 0),
        2
    ) AS on_time_delivery_rate_pct
FROM dw.dim_seller s
INNER JOIN dw.fact_sales fs
    ON s.seller_key = fs.seller_key
WHERE fs.order_status <> 'canceled'
GROUP BY
    s.seller_id,
    s.city,
    s.state;
GO

PRINT 'View [dw.vw_seller_performance] created.';
GO

-- ------------------------------------------------------------------------------
-- 3. View: Delivery & Logistical Performance by Customer State (dw.vw_delivery_performance)
-- ------------------------------------------------------------------------------
CREATE OR ALTER VIEW dw.vw_delivery_performance AS
SELECT
    c.state AS customer_state,
    d.year,
    d.month,
    d.month_name,
    COUNT(DISTINCT fs.order_id) AS completed_orders,
    ROUND(AVG(fs.delivery_days), 2) AS avg_delivery_days,
    ROUND(AVG(fs.delay_days), 2) AS avg_delay_days,
    ROUND(
        SUM(CASE WHEN fs.delay_days > 0 THEN 1.0 ELSE 0.0 END) * 100.0 / NULLIF(COUNT(fs.delay_days), 0),
        2
    ) AS late_delivery_rate_pct,
    ROUND(AVG(CAST(fs.review_score AS FLOAT)), 2) AS avg_review_score
FROM dw.fact_sales fs
INNER JOIN dw.dim_customer c
    ON fs.customer_key = c.customer_key
INNER JOIN dw.dim_date d
    ON fs.purchase_date_key = d.date_key
WHERE fs.order_status = 'delivered'
  AND fs.delivery_days IS NOT NULL
GROUP BY
    c.state,
    d.year,
    d.month,
    d.month_name;
GO

PRINT 'View [dw.vw_delivery_performance] created.';
GO
