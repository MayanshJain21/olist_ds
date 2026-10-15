-- ==============================================================================
-- Script: 05_load_facts.sql
-- Description: Idempotent facts load using INSERT ... WHERE NOT EXISTS.
-- Grain for fact_sales: One row per order item.
-- Grain for fact_payments: One row per payment installment/sequential.
-- Wrapped in an explicit TRANSACTION with structured TRY/CATCH error handling.
-- ==============================================================================

SET NOCOUNT ON;

BEGIN TRANSACTION;

BEGIN TRY
    PRINT '==================================================';
    PRINT 'STARTING FACT TABLES LOAD (IDEMPOTENT)';
    PRINT '==================================================';

    -- --------------------------------------------------------------------------
    -- 1. Load dw.fact_sales
    -- Grain: One row per order item.
    -- --------------------------------------------------------------------------
    PRINT 'Loading dw.fact_sales...';

    INSERT INTO dw.fact_sales (
        order_id,
        order_item_id,
        customer_key,
        seller_key,
        product_key,
        purchase_date_key,
        delivered_date_key,
        estimated_date_key,
        price,
        freight_value,
        delivery_days,
        delay_days,
        review_score,
        order_status,
        created_at
    )
    SELECT
        oi.order_id,
        oi.order_item_id,
        dc.customer_key,
        ds.seller_key,
        dp.product_key,
        dd_purch.date_key AS purchase_date_key,
        dd_deliv.date_key AS delivered_date_key,
        dd_est.date_key   AS estimated_date_key,
        oi.price,
        oi.freight_value,
        o.delivery_days,
        o.delay_days,
        r.review_score,
        o.order_status,
        SYSUTCDATETIME() AS created_at
    FROM staging.stg_order_items oi
    INNER JOIN staging.stg_orders o
        ON oi.order_id = o.order_id
    INNER JOIN staging.stg_customers c
        ON o.customer_id = c.customer_id
    INNER JOIN dw.dim_customer dc
        ON c.customer_unique_id = dc.customer_unique_id
    INNER JOIN dw.dim_seller ds
        ON oi.seller_id = ds.seller_id
    INNER JOIN dw.dim_product dp
        ON oi.product_id = dp.product_id
    INNER JOIN dw.dim_date dd_purch
        ON dd_purch.full_date = CAST(o.order_purchase_timestamp AS DATE)
    LEFT JOIN dw.dim_date dd_deliv
        ON dd_deliv.full_date = CAST(o.order_delivered_customer_date AS DATE)
    LEFT JOIN dw.dim_date dd_est
        ON dd_est.full_date = CAST(o.order_estimated_delivery_date AS DATE)
    LEFT JOIN staging.stg_order_reviews r
        ON o.order_id = r.order_id
    WHERE NOT EXISTS (
        SELECT 1
        FROM dw.fact_sales existing
        WHERE existing.order_id = oi.order_id
          AND existing.order_item_id = oi.order_item_id
    );

    PRINT 'dw.fact_sales load complete.';

    -- --------------------------------------------------------------------------
    -- 2. Load dw.fact_payments (Stretch fact table)
    -- Grain: One row per order payment.
    -- --------------------------------------------------------------------------
    PRINT 'Loading dw.fact_payments...';

    INSERT INTO dw.fact_payments (
        order_id,
        payment_sequential,
        customer_key,
        purchase_date_key,
        payment_type,
        payment_installments,
        payment_value,
        created_at
    )
    SELECT
        op.order_id,
        op.payment_sequential,
        dc.customer_key,
        dd_purch.date_key AS purchase_date_key,
        op.payment_type,
        op.payment_installments,
        op.payment_value,
        SYSUTCDATETIME() AS created_at
    FROM staging.stg_order_payments op
    INNER JOIN staging.stg_orders o
        ON op.order_id = o.order_id
    INNER JOIN staging.stg_customers c
        ON o.customer_id = c.customer_id
    INNER JOIN dw.dim_customer dc
        ON c.customer_unique_id = dc.customer_unique_id
    INNER JOIN dw.dim_date dd_purch
        ON dd_purch.full_date = CAST(o.order_purchase_timestamp AS DATE)
    WHERE NOT EXISTS (
        SELECT 1
        FROM dw.fact_payments existing
        WHERE existing.order_id = op.order_id
          AND existing.payment_sequential = op.payment_sequential
    );

    PRINT 'dw.fact_payments load complete.';

    COMMIT TRANSACTION;
    PRINT 'ALL FACT TABLES LOADED SUCCESSFULLY.';
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    PRINT 'ERROR DURING FACT TABLE LOAD:';
    PRINT ERROR_MESSAGE();
    THROW;
END CATCH;
GO
