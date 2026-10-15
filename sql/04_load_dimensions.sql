-- ==============================================================================
-- Script: 04_load_dimensions.sql
-- Description: Loads and upserts Star Schema dimensions using MERGE statements.
-- Wrapped in an explicit TRANSACTION with structured TRY/CATCH error handling.
-- ==============================================================================

SET NOCOUNT ON;

BEGIN TRANSACTION;

BEGIN TRY
    PRINT '==================================================';
    PRINT 'STARTING DIMENSION LOAD (MERGE / UPSERT)';
    PRINT '==================================================';

    -- --------------------------------------------------------------------------
    -- 1. Load dw.dim_date (Recursive CTE: 2016-01-01 to 2019-12-31)
    -- --------------------------------------------------------------------------
    PRINT 'Populating dw.dim_date (2016-2019)...';

    WITH DateSequence AS (
        SELECT CAST('2016-01-01' AS DATE) AS CalendarDate
        UNION ALL
        SELECT DATEADD(DAY, 1, CalendarDate)
        FROM DateSequence
        WHERE CalendarDate < CAST('2019-12-31' AS DATE)
    ),
    DateAttributes AS (
        SELECT
            (YEAR(CalendarDate) * 10000) + (MONTH(CalendarDate) * 100) + DAY(CalendarDate) AS date_key,
            CalendarDate AS full_date,
            YEAR(CalendarDate) AS year,
            DATEPART(QUARTER, CalendarDate) AS quarter,
            MONTH(CalendarDate) AS month,
            DATENAME(MONTH, CalendarDate) AS month_name,
            DAY(CalendarDate) AS day,
            DATEPART(WEEKDAY, CalendarDate) AS day_of_week,
            DATENAME(WEEKDAY, CalendarDate) AS day_name,
            CASE WHEN DATEPART(WEEKDAY, CalendarDate) IN (1, 7) THEN 1 ELSE 0 END AS is_weekend
        FROM DateSequence
    )
    MERGE INTO dw.dim_date AS Target
    USING DateAttributes AS Source
    ON (Target.date_key = Source.date_key)
    WHEN NOT MATCHED THEN
        INSERT (date_key, full_date, year, quarter, month, month_name, day, day_of_week, day_name, is_weekend)
        VALUES (Source.date_key, Source.full_date, Source.year, Source.quarter, Source.month,
                Source.month_name, Source.day, Source.day_of_week, Source.day_name, Source.is_weekend)
    WHEN MATCHED THEN
        UPDATE SET
            Target.full_date = Source.full_date,
            Target.year = Source.year,
            Target.quarter = Source.quarter,
            Target.month = Source.month,
            Target.month_name = Source.month_name,
            Target.day = Source.day,
            Target.day_of_week = Source.day_of_week,
            Target.day_name = Source.day_name,
            Target.is_weekend = Source.is_weekend
    OPTION (MAXRECURSION 2000);

    PRINT 'dw.dim_date load complete.';

    -- --------------------------------------------------------------------------
    -- 2. Load dw.dim_customer (Deduplicated on customer_unique_id)
    -- --------------------------------------------------------------------------
    PRINT 'Upserting dw.dim_customer...';

    WITH DeduplicatedCustomers AS (
        SELECT
            customer_unique_id,
            customer_zip_code_prefix,
            customer_city,
            customer_state,
            ROW_NUMBER() OVER(
                PARTITION BY customer_unique_id
                ORDER BY customer_id DESC
            ) AS row_num
        FROM staging.stg_customers
    )
    MERGE INTO dw.dim_customer AS Target
    USING (
        SELECT
            customer_unique_id,
            customer_zip_code_prefix,
            customer_city,
            customer_state
        FROM DeduplicatedCustomers
        WHERE row_num = 1
    ) AS Source
    ON (Target.customer_unique_id = Source.customer_unique_id)
    WHEN MATCHED AND (
        ISNULL(Target.zip_code_prefix, '') <> ISNULL(Source.customer_zip_code_prefix, '') OR
        ISNULL(Target.city, '') <> ISNULL(Source.customer_city, '') OR
        ISNULL(Target.state, '') <> ISNULL(Source.customer_state, '')
    ) THEN
        UPDATE SET
            Target.zip_code_prefix = Source.customer_zip_code_prefix,
            Target.city = Source.customer_city,
            Target.state = Source.customer_state,
            Target.updated_at = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (customer_unique_id, zip_code_prefix, city, state, created_at, updated_at)
        VALUES (Source.customer_unique_id, Source.customer_zip_code_prefix, Source.customer_city, Source.customer_state, SYSUTCDATETIME(), SYSUTCDATETIME());

    PRINT 'dw.dim_customer upsert complete.';

    -- --------------------------------------------------------------------------
    -- 3. Load dw.dim_seller
    -- --------------------------------------------------------------------------
    PRINT 'Upserting dw.dim_seller...';

    MERGE INTO dw.dim_seller AS Target
    USING (
        SELECT DISTINCT
            seller_id,
            seller_zip_code_prefix,
            seller_city,
            seller_state
        FROM staging.stg_sellers
    ) AS Source
    ON (Target.seller_id = Source.seller_id)
    WHEN MATCHED AND (
        ISNULL(Target.zip_code_prefix, '') <> ISNULL(Source.seller_zip_code_prefix, '') OR
        ISNULL(Target.city, '') <> ISNULL(Source.seller_city, '') OR
        ISNULL(Target.state, '') <> ISNULL(Source.seller_state, '')
    ) THEN
        UPDATE SET
            Target.zip_code_prefix = Source.seller_zip_code_prefix,
            Target.city = Source.seller_city,
            Target.state = Source.seller_state,
            Target.updated_at = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (seller_id, zip_code_prefix, city, state, created_at, updated_at)
        VALUES (Source.seller_id, Source.seller_zip_code_prefix, Source.seller_city, Source.seller_state, SYSUTCDATETIME(), SYSUTCDATETIME());

    PRINT 'dw.dim_seller upsert complete.';

    -- --------------------------------------------------------------------------
    -- 4. Load dw.dim_product
    -- --------------------------------------------------------------------------
    PRINT 'Upserting dw.dim_product...';

    MERGE INTO dw.dim_product AS Target
    USING (
        SELECT DISTINCT
            product_id,
            ISNULL(product_category_name, 'unknown') AS category_name,
            ISNULL(product_category_name_english, 'unknown') AS category_name_english,
            product_name_length,
            product_description_length,
            product_photos_qty,
            product_weight_g,
            product_length_cm,
            product_height_cm,
            product_width_cm
        FROM staging.stg_products
    ) AS Source
    ON (Target.product_id = Source.product_id)
    WHEN MATCHED THEN
        UPDATE SET
            Target.category_name = Source.category_name,
            Target.category_name_english = Source.category_name_english,
            Target.name_length = Source.product_name_length,
            Target.description_length = Source.product_description_length,
            Target.photos_qty = Source.product_photos_qty,
            Target.weight_g = Source.product_weight_g,
            Target.length_cm = Source.product_length_cm,
            Target.height_cm = Source.product_height_cm,
            Target.width_cm = Source.product_width_cm,
            Target.updated_at = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (
            product_id,
            category_name,
            category_name_english,
            name_length,
            description_length,
            photos_qty,
            weight_g,
            length_cm,
            height_cm,
            width_cm,
            created_at,
            updated_at
        )
        VALUES (
            Source.product_id,
            Source.category_name,
            Source.category_name_english,
            Source.product_name_length,
            Source.product_description_length,
            Source.product_photos_qty,
            Source.product_weight_g,
            Source.product_length_cm,
            Source.product_height_cm,
            Source.product_width_cm,
            SYSUTCDATETIME(),
            SYSUTCDATETIME()
        );

    PRINT 'dw.dim_product upsert complete.';

    COMMIT TRANSACTION;
    PRINT 'ALL DIMENSIONS LOADED SUCCESSFULLY.';
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    PRINT 'ERROR DURING DIMENSION LOAD:';
    PRINT ERROR_MESSAGE();
    THROW;
END CATCH;
GO
