-- ==============================================================================
-- Script: 02_staging_tables.sql
-- Description: Creates staging tables for raw/cleaned Parquet ingestion in Azure SQL.
-- Idempotent: checks for existence before creation.
-- ==============================================================================

-- 1. Orders Staging Table
IF OBJECT_ID('staging.stg_orders', 'U') IS NULL
BEGIN
    CREATE TABLE staging.stg_orders (
        order_id VARCHAR(50) NOT NULL,
        customer_id VARCHAR(50) NOT NULL,
        order_status VARCHAR(30) NOT NULL,
        order_purchase_timestamp DATETIME2 NULL,
        order_approved_at DATETIME2 NULL,
        order_delivered_carrier_date DATETIME2 NULL,
        order_delivered_customer_date DATETIME2 NULL,
        order_estimated_delivery_date DATETIME2 NULL,
        delivery_days DECIMAL(10, 2) NULL,
        delay_days DECIMAL(10, 2) NULL
    );
    PRINT 'Table [staging.stg_orders] created.';
END;
GO

-- 2. Order Items Staging Table
IF OBJECT_ID('staging.stg_order_items', 'U') IS NULL
BEGIN
    CREATE TABLE staging.stg_order_items (
        order_id VARCHAR(50) NOT NULL,
        order_item_id INT NOT NULL,
        product_id VARCHAR(50) NOT NULL,
        seller_id VARCHAR(50) NOT NULL,
        shipping_limit_date DATETIME2 NULL,
        price DECIMAL(10, 2) NOT NULL,
        freight_value DECIMAL(10, 2) NOT NULL
    );
    PRINT 'Table [staging.stg_order_items] created.';
END;
GO

-- 3. Order Payments Staging Table
IF OBJECT_ID('staging.stg_order_payments', 'U') IS NULL
BEGIN
    CREATE TABLE staging.stg_order_payments (
        order_id VARCHAR(50) NOT NULL,
        payment_sequential INT NOT NULL,
        payment_type VARCHAR(30) NOT NULL,
        payment_installments INT NOT NULL,
        payment_value DECIMAL(10, 2) NOT NULL
    );
    PRINT 'Table [staging.stg_order_payments] created.';
END;
GO

-- 4. Order Reviews Staging Table
IF OBJECT_ID('staging.stg_order_reviews', 'U') IS NULL
BEGIN
    CREATE TABLE staging.stg_order_reviews (
        review_id VARCHAR(50) NOT NULL,
        order_id VARCHAR(50) NOT NULL,
        review_score INT NOT NULL,
        review_comment_title NVARCHAR(255) NULL,
        review_comment_message NVARCHAR(MAX) NULL,
        review_creation_date DATETIME2 NULL,
        review_answer_timestamp DATETIME2 NULL
    );
    PRINT 'Table [staging.stg_order_reviews] created.';
END;
GO

-- 5. Products Staging Table
IF OBJECT_ID('staging.stg_products', 'U') IS NULL
BEGIN
    CREATE TABLE staging.stg_products (
        product_id VARCHAR(50) NOT NULL,
        product_category_name NVARCHAR(100) NULL,
        product_name_length INT NULL,
        product_description_length INT NULL,
        product_photos_qty INT NULL,
        product_weight_g INT NULL,
        product_length_cm INT NULL,
        product_height_cm INT NULL,
        product_width_cm INT NULL,
        product_category_name_english NVARCHAR(100) NULL
    );
    PRINT 'Table [staging.stg_products] created.';
END;
GO

-- 6. Customers Staging Table
IF OBJECT_ID('staging.stg_customers', 'U') IS NULL
BEGIN
    CREATE TABLE staging.stg_customers (
        customer_id VARCHAR(50) NOT NULL,
        customer_unique_id VARCHAR(50) NOT NULL,
        customer_zip_code_prefix VARCHAR(10) NULL,
        customer_city NVARCHAR(100) NULL,
        customer_state VARCHAR(5) NULL
    );
    PRINT 'Table [staging.stg_customers] created.';
END;
GO

-- 7. Sellers Staging Table
IF OBJECT_ID('staging.stg_sellers', 'U') IS NULL
BEGIN
    CREATE TABLE staging.stg_sellers (
        seller_id VARCHAR(50) NOT NULL,
        seller_zip_code_prefix VARCHAR(10) NULL,
        seller_city NVARCHAR(100) NULL,
        seller_state VARCHAR(5) NULL
    );
    PRINT 'Table [staging.stg_sellers] created.';
END;
GO

-- 8. Geolocation Staging Table
IF OBJECT_ID('staging.stg_geolocation', 'U') IS NULL
BEGIN
    CREATE TABLE staging.stg_geolocation (
        geolocation_zip_code_prefix VARCHAR(10) NOT NULL,
        geolocation_lat DECIMAL(10, 6) NULL,
        geolocation_lng DECIMAL(10, 6) NULL,
        geolocation_city NVARCHAR(100) NULL,
        geolocation_state VARCHAR(5) NULL
    );
    PRINT 'Table [staging.stg_geolocation] created.';
END;
GO
