-- ==============================================================================
-- Script: 03_warehouse_tables.sql
-- Description: DDL for the Star Schema dimensional model in the 'dw' schema.
-- Includes surrogate keys, enterprise constraints, persisted computed columns, and indexes.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Dimension: Date (dw.dim_date)
-- ------------------------------------------------------------------------------
IF OBJECT_ID('dw.dim_date', 'U') IS NULL
BEGIN
    CREATE TABLE dw.dim_date (
        date_key INT NOT NULL,                  -- YYYYMMDD format (e.g., 20170115)
        full_date DATE NOT NULL,
        year INT NOT NULL,
        quarter INT NOT NULL,
        month INT NOT NULL,
        month_name VARCHAR(20) NOT NULL,
        day INT NOT NULL,
        day_of_week INT NOT NULL,               -- 1 = Sunday ... 7 = Saturday
        day_name VARCHAR(20) NOT NULL,
        is_weekend BIT NOT NULL,
        CONSTRAINT PK_dim_date PRIMARY KEY CLUSTERED (date_key),
        CONSTRAINT UQ_dim_date_full_date UNIQUE (full_date)
    );
    PRINT 'Dimension [dw.dim_date] created.';
END;
GO

-- ------------------------------------------------------------------------------
-- 2. Dimension: Customer (dw.dim_customer)
-- Keyed on customer_unique_id (the real customer entity in Olist)
-- ------------------------------------------------------------------------------
IF OBJECT_ID('dw.dim_customer', 'U') IS NULL
BEGIN
    CREATE TABLE dw.dim_customer (
        customer_key INT IDENTITY(1, 1) NOT NULL,
        customer_unique_id VARCHAR(50) NOT NULL,
        zip_code_prefix VARCHAR(10) NULL,
        city NVARCHAR(100) NULL,
        state VARCHAR(5) NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_dim_customer PRIMARY KEY CLUSTERED (customer_key),
        CONSTRAINT UQ_dim_customer_unique_id UNIQUE (customer_unique_id)
    );
    PRINT 'Dimension [dw.dim_customer] created.';
END;
GO

-- ------------------------------------------------------------------------------
-- 3. Dimension: Seller (dw.dim_seller)
-- ------------------------------------------------------------------------------
IF OBJECT_ID('dw.dim_seller', 'U') IS NULL
BEGIN
    CREATE TABLE dw.dim_seller (
        seller_key INT IDENTITY(1, 1) NOT NULL,
        seller_id VARCHAR(50) NOT NULL,
        zip_code_prefix VARCHAR(10) NULL,
        city NVARCHAR(100) NULL,
        state VARCHAR(5) NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_dim_seller PRIMARY KEY CLUSTERED (seller_key),
        CONSTRAINT UQ_dim_seller_id UNIQUE (seller_id)
    );
    PRINT 'Dimension [dw.dim_seller] created.';
END;
GO

-- ------------------------------------------------------------------------------
-- 4. Dimension: Product (dw.dim_product)
-- ------------------------------------------------------------------------------
IF OBJECT_ID('dw.dim_product', 'U') IS NULL
BEGIN
    CREATE TABLE dw.dim_product (
        product_key INT IDENTITY(1, 1) NOT NULL,
        product_id VARCHAR(50) NOT NULL,
        category_name NVARCHAR(100) NOT NULL,
        category_name_english NVARCHAR(100) NOT NULL,
        name_length INT NULL,
        description_length INT NULL,
        photos_qty INT NULL,
        weight_g INT NULL,
        length_cm INT NULL,
        height_cm INT NULL,
        width_cm INT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_dim_product PRIMARY KEY CLUSTERED (product_key),
        CONSTRAINT UQ_dim_product_id UNIQUE (product_id)
    );
    PRINT 'Dimension [dw.dim_product] created.';
END;
GO

-- ------------------------------------------------------------------------------
-- 5. Fact: Sales (dw.fact_sales)
-- Grain: One row per order item.
-- Foreign keys to all dimensions, plus role-playing date dimensions.
-- ------------------------------------------------------------------------------
IF OBJECT_ID('dw.fact_sales', 'U') IS NULL
BEGIN
    CREATE TABLE dw.fact_sales (
        sales_key BIGINT IDENTITY(1, 1) NOT NULL,
        order_id VARCHAR(50) NOT NULL,
        order_item_id INT NOT NULL,
        customer_key INT NOT NULL,
        seller_key INT NOT NULL,
        product_key INT NOT NULL,
        purchase_date_key INT NOT NULL,
        delivered_date_key INT NULL,
        estimated_date_key INT NULL,
        price DECIMAL(10, 2) NOT NULL,
        freight_value DECIMAL(10, 2) NOT NULL,
        total_value AS (price + freight_value) PERSISTED,
        delivery_days DECIMAL(10, 2) NULL,
        delay_days DECIMAL(10, 2) NULL,
        review_score INT NULL,
        order_status VARCHAR(30) NOT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_fact_sales PRIMARY KEY CLUSTERED (sales_key),
        CONSTRAINT UQ_fact_sales_order_item UNIQUE (order_id, order_item_id),
        CONSTRAINT FK_fact_sales_customer FOREIGN KEY (customer_key) REFERENCES dw.dim_customer (customer_key),
        CONSTRAINT FK_fact_sales_seller FOREIGN KEY (seller_key) REFERENCES dw.dim_seller (seller_key),
        CONSTRAINT FK_fact_sales_product FOREIGN KEY (product_key) REFERENCES dw.dim_product (product_key),
        CONSTRAINT FK_fact_sales_purchase_date FOREIGN KEY (purchase_date_key) REFERENCES dw.dim_date (date_key),
        CONSTRAINT FK_fact_sales_delivered_date FOREIGN KEY (delivered_date_key) REFERENCES dw.dim_date (date_key),
        CONSTRAINT FK_fact_sales_estimated_date FOREIGN KEY (estimated_date_key) REFERENCES dw.dim_date (date_key)
    );

    -- Create nonclustered performance indexes for Star Schema analytics
    CREATE NONCLUSTERED INDEX IX_fact_sales_purchase_date ON dw.fact_sales (purchase_date_key);
    CREATE NONCLUSTERED INDEX IX_fact_sales_product ON dw.fact_sales (product_key);
    CREATE NONCLUSTERED INDEX IX_fact_sales_seller ON dw.fact_sales (seller_key);
    CREATE NONCLUSTERED INDEX IX_fact_sales_customer ON dw.fact_sales (customer_key);

    PRINT 'Fact Table [dw.fact_sales] created with indexes.';
END;
GO

-- ------------------------------------------------------------------------------
-- 6. Stretch Fact: Payments (dw.fact_payments)
-- Grain: One row per order payment.
-- ------------------------------------------------------------------------------
IF OBJECT_ID('dw.fact_payments', 'U') IS NULL
BEGIN
    CREATE TABLE dw.fact_payments (
        payment_key BIGINT IDENTITY(1, 1) NOT NULL,
        order_id VARCHAR(50) NOT NULL,
        payment_sequential INT NOT NULL,
        customer_key INT NOT NULL,
        purchase_date_key INT NOT NULL,
        payment_type VARCHAR(30) NOT NULL,
        payment_installments INT NOT NULL,
        payment_value DECIMAL(10, 2) NOT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),

        CONSTRAINT PK_fact_payments PRIMARY KEY CLUSTERED (payment_key),
        CONSTRAINT UQ_fact_payments UNIQUE (order_id, payment_sequential),
        CONSTRAINT FK_fact_payments_customer FOREIGN KEY (customer_key) REFERENCES dw.dim_customer (customer_key),
        CONSTRAINT FK_fact_payments_purchase_date FOREIGN KEY (purchase_date_key) REFERENCES dw.dim_date (date_key)
    );

    CREATE NONCLUSTERED INDEX IX_fact_payments_purchase_date ON dw.fact_payments (purchase_date_key);
    CREATE NONCLUSTERED INDEX IX_fact_payments_customer ON dw.fact_payments (customer_key);

    PRINT 'Fact Table [dw.fact_payments] created with indexes.';
END;
GO
