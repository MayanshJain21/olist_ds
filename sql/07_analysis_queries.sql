-- ==============================================================================
-- Script: 07_analysis_queries.sql
-- Description: Advanced analytical SQL queries showcasing Star Schema querying,
-- CTEs, window functions (LAG, RANK, DENSE_RANK, SUM OVER), and business KPIs.
-- ==============================================================================

-- ==============================================================================
-- Query 1: Monthly Revenue & Month-over-Month (MoM) Growth
-- Technique: CTE + LAG() Window Function
-- Business Value: Tracks sales trajectory, seasonality, and revenue momentum.
-- ==============================================================================
WITH MonthlySales AS (
    SELECT
        d.year,
        d.month,
        d.month_name,
        (d.year * 100) + d.month AS year_month_key,
        SUM(fs.total_value) AS current_month_revenue,
        COUNT(DISTINCT fs.order_id) AS total_orders
    FROM dw.fact_sales fs
    INNER JOIN dw.dim_date d
        ON fs.purchase_date_key = d.date_key
    WHERE fs.order_status <> 'canceled'
    GROUP BY
        d.year,
        d.month,
        d.month_name,
        (d.year * 100) + d.month
)
SELECT
    year,
    month,
    month_name,
    current_month_revenue,
    total_orders,
    LAG(current_month_revenue, 1) OVER (ORDER BY year_month_key) AS previous_month_revenue,
    ROUND(
        (current_month_revenue - LAG(current_month_revenue, 1) OVER (ORDER BY year_month_key))
        * 100.0 / NULLIF(LAG(current_month_revenue, 1) OVER (ORDER BY year_month_key), 0),
        2
    ) AS mom_revenue_growth_pct
FROM MonthlySales
ORDER BY year_month_key;


-- ==============================================================================
-- Query 2: Top 3 Sellers per State
-- Technique: CTE + DENSE_RANK() OVER (PARTITION BY state ORDER BY revenue DESC)
-- Business Value: Identifies premier regional merchant partners for account management.
-- ==============================================================================
WITH SellerRevenueByState AS (
    SELECT
        s.state AS seller_state,
        s.seller_id,
        s.city AS seller_city,
        COUNT(DISTINCT fs.order_id) AS total_orders,
        SUM(fs.total_value) AS total_revenue,
        ROUND(AVG(CAST(fs.review_score AS FLOAT)), 2) AS avg_review_score,
        DENSE_RANK() OVER (
            PARTITION BY s.state
            ORDER BY SUM(fs.total_value) DESC
        ) AS state_rank
    FROM dw.fact_sales fs
    INNER JOIN dw.dim_seller s
        ON fs.seller_key = s.seller_key
    WHERE fs.order_status <> 'canceled'
    GROUP BY
        s.state,
        s.seller_id,
        s.city
)
SELECT
    seller_state,
    state_rank,
    seller_id,
    seller_city,
    total_orders,
    total_revenue,
    avg_review_score
FROM SellerRevenueByState
WHERE state_rank <= 3
ORDER BY
    seller_state ASC,
    state_rank ASC;


-- ==============================================================================
-- Query 3: Average Delivery Delay & Review Score by Customer State
-- Technique: Aggregations + Conditional Metric Filtering
-- Business Value: Diagnoses regional logistics bottlenecks and customer satisfaction correlation.
-- ==============================================================================
SELECT
    c.state AS customer_state,
    COUNT(DISTINCT fs.order_id) AS delivered_orders,
    ROUND(AVG(fs.delivery_days), 2) AS avg_actual_delivery_days,
    ROUND(AVG(fs.delay_days), 2) AS avg_delay_days,
    ROUND(
        SUM(CASE WHEN fs.delay_days > 0 THEN 1.0 ELSE 0.0 END) * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS delayed_orders_rate_pct,
    ROUND(AVG(CAST(fs.review_score AS FLOAT)), 2) AS avg_review_score
FROM dw.fact_sales fs
INNER JOIN dw.dim_customer c
    ON fs.customer_key = c.customer_key
WHERE fs.order_status = 'delivered'
  AND fs.delivery_days IS NOT NULL
GROUP BY
    c.state
ORDER BY
    avg_delay_days DESC;


-- ==============================================================================
-- Query 4: Top 10 Product Categories by Revenue with % Share of Total
-- Technique: Window Function SUM() OVER () for Global Aggregation within CTE
-- Business Value: Reveals category concentration and portfolio drivers.
-- ==============================================================================
WITH CategorySales AS (
    SELECT
        p.category_name_english,
        COUNT(fs.order_item_id) AS items_sold,
        SUM(fs.total_value) AS category_revenue
    FROM dw.fact_sales fs
    INNER JOIN dw.dim_product p
        ON fs.product_key = p.product_key
    WHERE fs.order_status <> 'canceled'
    GROUP BY
        p.category_name_english
),
RankedCategories AS (
    SELECT
        category_name_english,
        items_sold,
        category_revenue,
        SUM(category_revenue) OVER () AS total_enterprise_revenue,
        ROUND(
            category_revenue * 100.0 / NULLIF(SUM(category_revenue) OVER (), 0),
            2
        ) AS revenue_share_pct,
        ROW_NUMBER() OVER (ORDER BY category_revenue DESC) AS category_rank
    FROM CategorySales
)
SELECT
    category_rank,
    category_name_english,
    items_sold,
    category_revenue,
    revenue_share_pct
FROM RankedCategories
WHERE category_rank <= 10
ORDER BY category_rank ASC;


-- ==============================================================================
-- Query 5: Repeat-Customer Rate
-- Technique: CTE counting distinct orders per customer_unique_id
-- Business Value: Measures customer retention and customer lifetime value (LTV).
-- ==============================================================================
WITH CustomerOrderCounts AS (
    SELECT
        c.customer_unique_id,
        COUNT(DISTINCT fs.order_id) AS order_count,
        SUM(fs.total_value) AS lifetime_spend
    FROM dw.fact_sales fs
    INNER JOIN dw.dim_customer c
        ON fs.customer_key = c.customer_key
    WHERE fs.order_status <> 'canceled'
    GROUP BY
        c.customer_unique_id
)
SELECT
    COUNT(*) AS total_unique_customers,
    SUM(CASE WHEN order_count > 1 THEN 1 ELSE 0 END) AS repeat_customers_count,
    SUM(CASE WHEN order_count = 1 THEN 1 ELSE 0 END) AS one_time_customers_count,
    ROUND(
        SUM(CASE WHEN order_count > 1 THEN 1.0 ELSE 0.0 END) * 100.0 / NULLIF(COUNT(*), 0),
        2
    ) AS repeat_customer_rate_pct,
    ROUND(
        AVG(CASE WHEN order_count > 1 THEN lifetime_spend ELSE NULL END),
        2
    ) AS avg_repeat_customer_spend,
    ROUND(
        AVG(CASE WHEN order_count = 1 THEN lifetime_spend ELSE NULL END),
        2
    ) AS avg_one_time_customer_spend
FROM CustomerOrderCounts;


-- ==============================================================================
-- Query 6: Cumulative Revenue by Month (Running Total)
-- Technique: SUM() OVER (ORDER BY ... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
-- Business Value: Shows cumulative enterprise sales curve over time.
-- ==============================================================================
WITH MonthlyTotals AS (
    SELECT
        d.year,
        d.month,
        d.month_name,
        (d.year * 100) + d.month AS year_month_key,
        SUM(fs.total_value) AS monthly_revenue
    FROM dw.fact_sales fs
    INNER JOIN dw.dim_date d
        ON fs.purchase_date_key = d.date_key
    WHERE fs.order_status <> 'canceled'
    GROUP BY
        d.year,
        d.month,
        d.month_name,
        (d.year * 100) + d.month
)
SELECT
    year,
    month,
    month_name,
    monthly_revenue,
    SUM(monthly_revenue) OVER (
        ORDER BY year_month_key
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_running_revenue
FROM MonthlyTotals
ORDER BY year_month_key;


-- ==============================================================================
-- Query 7: Late-Delivery Rate vs. Average Review Score
-- Technique: Binned conditional grouping on delivery delay
-- Business Value: Quantifies direct empirical impact of delivery delays on CSAT.
-- ==============================================================================
WITH DeliveryPerformanceBinned AS (
    SELECT
        fs.order_id,
        fs.review_score,
        CASE
            WHEN fs.delay_days <= -3 THEN 'Early by >3 days'
            WHEN fs.delay_days BETWEEN -2.99 AND 0 THEN 'On-time (0-3 days early)'
            WHEN fs.delay_days BETWEEN 0.01 AND 3 THEN 'Minor Delay (1-3 days late)'
            WHEN fs.delay_days BETWEEN 3.01 AND 7 THEN 'Moderate Delay (4-7 days late)'
            WHEN fs.delay_days > 7 THEN 'Severe Delay (>7 days late)'
            ELSE 'Unknown'
        END AS delivery_performance_bucket,
        CASE WHEN fs.delay_days > 0 THEN 1 ELSE 0 END AS is_late
    FROM dw.fact_sales fs
    WHERE fs.order_status = 'delivered'
      AND fs.delivery_days IS NOT NULL
      AND fs.review_score IS NOT NULL
)
SELECT
    delivery_performance_bucket,
    COUNT(DISTINCT order_id) AS total_orders,
    ROUND(AVG(CAST(review_score AS FLOAT)), 2) AS avg_review_score,
    SUM(CASE WHEN review_score = 5 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_5_star_reviews,
    SUM(CASE WHEN review_score = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS pct_1_star_reviews
FROM DeliveryPerformanceBinned
GROUP BY
    delivery_performance_bucket
ORDER BY
    avg_review_score DESC;


-- ==============================================================================
-- Query 8: Revenue by Day of Week and Weekend vs. Weekday
-- Technique: Dimension grouping on Date dimension attributes
-- Business Value: Informs marketing budget pacing and discount campaign timing.
-- ==============================================================================
SELECT
    d.day_of_week,
    d.day_name,
    CASE WHEN d.is_weekend = 1 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
    COUNT(DISTINCT fs.order_id) AS total_orders,
    SUM(fs.total_value) AS total_revenue,
    ROUND(AVG(fs.total_value), 2) AS avg_item_revenue,
    ROUND(
        SUM(fs.total_value) * 100.0 / SUM(SUM(fs.total_value)) OVER (),
        2
    ) AS pct_of_total_revenue
FROM dw.fact_sales fs
INNER JOIN dw.dim_date d
    ON fs.purchase_date_key = d.date_key
WHERE fs.order_status <> 'canceled'
GROUP BY
    d.day_of_week,
    d.day_name,
    d.is_weekend
ORDER BY
    d.day_of_week ASC;
