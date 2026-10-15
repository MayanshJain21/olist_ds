# Olist Data Warehouse Architecture & Dimensional Design

## 1. End-to-End Pipeline Architecture

The **olist-data-warehouse** is designed as a modern ELT/ETL hybrid data pipeline combining **Python** for file processing and data quality validation, **Azure Blob Storage / ADLS Gen2** for cloud data lake storage, and **Azure SQL Database** for dimensional warehousing and analytical querying.

```mermaid
flowchart TD
    subgraph Data_Source["1. Ingestion Layer"]
        Kaggle["Kaggle Olist Dataset<br/>(9 CSV Files)"]
        LocalRaw["Local Disk<br/>(data/raw/)"]
        AzureRaw["Azure Blob Storage<br/>(Container: raw)"]
        Kaggle --> LocalRaw
        LocalRaw -->|src/ingest.py| AzureRaw
    end

    subgraph Transformation_Layer["2. Cleaning & Validation Layer"]
        Clean["src/clean.py<br/>- Timestamp Parsing (5 cols)<br/>- Geo Aggregation (mean lat/lng)<br/>- Category Translation Join<br/>- Review Deduplication (keep latest)<br/>- Exact Deduplication"]
        Validate["src/validate.py<br/>(Data Quality Suite)<br/>- Duplicate order_id check<br/>- Null timestamp check<br/>- Price & freight > 0<br/>- Referential Integrity FKs<br/>- Review scores in [1, 5]"]
        Parquet["Cleaned Parquet Files<br/>(data/processed/)"]
        AzureProc["Azure Blob Storage<br/>(Container: processed)"]

        LocalRaw --> Clean
        Clean --> Parquet
        Parquet --> Validate
        Parquet -.->|Optional Upload| AzureProc
    end

    subgraph Staging_Layer["3. Staging Layer (Azure SQL)"]
        StgTables["Staging Schema (staging.*)<br/>- stg_orders<br/>- stg_order_items<br/>- stg_order_payments<br/>- stg_order_reviews<br/>- stg_products<br/>- stg_customers<br/>- stg_sellers<br/>- stg_geolocation"]
        Validate -->|src/load_staging.py<br/>SQLAlchemy + fast_executemany| StgTables
    end

    subgraph Warehouse_Layer["4. Star Schema Dimensional Warehouse (dw.*)"]
        DimDate["dw.dim_date<br/>(2016-2019 Recursive CTE)"]
        DimCust["dw.dim_customer<br/>(Keyed on customer_unique_id)"]
        DimSeller["dw.dim_seller"]
        DimProd["dw.dim_product<br/>(PT & EN Categories)"]
        FactSales["dw.fact_sales<br/>(Grain: 1 row per order item)"]
        FactPay["dw.fact_payments<br/>(Grain: 1 row per payment)"]

        StgTables -->|04_load_dimensions.sql (MERGE)| DimDate
        StgTables -->|04_load_dimensions.sql (MERGE)| DimCust
        StgTables -->|04_load_dimensions.sql (MERGE)| DimSeller
        StgTables -->|04_load_dimensions.sql (MERGE)| DimProd

        StgTables -->|05_load_facts.sql (INSERT WHERE NOT EXISTS)| FactSales
        StgTables -->|05_load_facts.sql (INSERT WHERE NOT EXISTS)| FactPay

        DimDate -.-> FactSales
        DimCust -.-> FactSales
        DimSeller -.-> FactSales
        DimProd -.-> FactSales

        DimDate -.-> FactPay
        DimCust -.-> FactPay
    end

    subgraph Analytics_Layer["5. Analytics & Business Intelligence"]
        Views["dw.vw_monthly_revenue<br/>dw.vw_seller_performance<br/>dw.vw_delivery_performance"]
        Queries["sql/07_analysis_queries.sql<br/>- MoM Revenue Growth (LAG)<br/>- Top 3 Sellers/State (RANK)<br/>- Repeat Customer Rate<br/>- Cumulative Revenue (SUM OVER)"]
        PowerBI["BI & Dashboards<br/>(Power BI / Excel / Tableau)"]

        FactSales --> Views
        FactPay --> Views
        Views --> Queries
        Views --> PowerBI
    end

    classDef source fill:#E1F5FE,stroke:#0288D1,stroke-width:2px;
    classDef transform fill:#FFF3E0,stroke:#F57C00,stroke-width:2px;
    classDef staging fill:#EDE7F6,stroke:#512DA8,stroke-width:2px;
    classDef warehouse fill:#E8F5E9,stroke:#388E3C,stroke-width:2px;
    classDef analytics fill:#FCE4EC,stroke:#C2185B,stroke-width:2px;

    class Kaggle,LocalRaw,AzureRaw source;
    class Clean,Validate,Parquet,AzureProc transform;
    class StgTables staging;
    class DimDate,DimCust,DimSeller,DimProd,FactSales,FactPay warehouse;
    class Views,Queries,PowerBI analytics;
```

---

## 2. Dimensional Data Model (Star Schema)

The analytical data warehouse follows Kimball star schema principles to optimize analytical query throughput, minimize JOIN complexity, and enable drill-down slice-and-dice reporting.

```mermaid
erDiagram
    dim_date ||--o{ fact_sales : "purchase_date_key"
    dim_date ||--o{ fact_sales : "delivered_date_key"
    dim_date ||--o{ fact_sales : "estimated_date_key"
    dim_customer ||--o{ fact_sales : "customer_key"
    dim_seller ||--o{ fact_sales : "seller_key"
    dim_product ||--o{ fact_sales : "product_key"
    dim_customer ||--o{ fact_payments : "customer_key"
    dim_date ||--o{ fact_payments : "purchase_date_key"

    dim_date {
        int date_key PK "YYYYMMDD format"
        date full_date UK "Calendar Date"
        int year "Year"
        int quarter "Quarter (1-4)"
        int month "Month number (1-12)"
        varchar month_name "Month name (January...)"
        int day "Day of month"
        int day_of_week "1=Sunday ... 7=Saturday"
        varchar day_name "Day name (Sunday...)"
        bit is_weekend "1 if Weekend, 0 if Weekday"
    }

    dim_customer {
        int customer_key PK "Surrogate Key (Identity)"
        varchar customer_unique_id UK "Natural Business Key"
        varchar zip_code_prefix "Zip prefix"
        nvarchar city "Customer City"
        varchar state "State Code (SP, RJ...)"
        datetime2 created_at "Record Creation Timestamp"
        datetime2 updated_at "Record Update Timestamp"
    }

    dim_seller {
        int seller_key PK "Surrogate Key (Identity)"
        varchar seller_id UK "Natural Business Key"
        varchar zip_code_prefix "Zip prefix"
        nvarchar city "Seller City"
        varchar state "State Code (SP, RJ...)"
        datetime2 created_at "Record Creation Timestamp"
        datetime2 updated_at "Record Update Timestamp"
    }

    dim_product {
        int product_key PK "Surrogate Key (Identity)"
        varchar product_id UK "Natural Business Key"
        nvarchar category_name "Portuguese Category Name"
        nvarchar category_name_english "English Category Name"
        int name_length "Character length"
        int description_length "Character length"
        int photos_qty "Number of photos"
        int weight_g "Weight in grams"
        int length_cm "Length in cm"
        int height_cm "Height in cm"
        int width_cm "Width in cm"
        datetime2 created_at "Record Creation Timestamp"
        datetime2 updated_at "Record Update Timestamp"
    }

    fact_sales {
        bigint sales_key PK "Surrogate Key (Identity)"
        varchar order_id "Order Identifier"
        int order_item_id "Item sequential number"
        int customer_key FK "References dim_customer"
        int seller_key FK "References dim_seller"
        int product_key FK "References dim_product"
        int purchase_date_key FK "References dim_date"
        int delivered_date_key FK "References dim_date (nullable)"
        int estimated_date_key FK "References dim_date (nullable)"
        decimal price "Item price"
        decimal freight_value "Item shipping cost"
        decimal total_value "Persisted: price + freight"
        decimal delivery_days "Actual days to deliver"
        decimal delay_days "Days late vs estimate"
        int review_score "Customer rating (1-5)"
        varchar order_status "Order status (delivered...)"
        datetime2 created_at "Insert Timestamp"
    }

    fact_payments {
        bigint payment_key PK "Surrogate Key (Identity)"
        varchar order_id "Order Identifier"
        int payment_sequential "Payment sequence number"
        int customer_key FK "References dim_customer"
        int purchase_date_key FK "References dim_date"
        varchar payment_type "credit_card, boleto..."
        int payment_installments "Number of installments"
        decimal payment_value "Transaction amount"
        datetime2 created_at "Insert Timestamp"
    }
```

---

## 3. Dimensional Modeling Design Decisions

### 3.1 Grains Defined
- **`dw.fact_sales`**: **One row per order item**. An order in Olist may contain multiple items across distinct products and sellers. Maintaining the item-level grain ensures zero loss of detail, enabling accurate product-level and seller-level margin calculations.
- **`dw.fact_payments`**: **One row per payment installment/sequential transaction**. Enables financial reconciliation against total order value and analysis of payment methods (credit card installments vs. cash boleto).

### 3.2 Handling Customer Entities (`customer_id` vs `customer_unique_id`)
In the raw Olist dataset, `customer_id` is an ephemeral token generated per order. The true real-world entity is `customer_unique_id`. Modeling `dim_customer` keyed on `customer_unique_id` allows accurate calculation of **repeat purchase rates**, **customer lifetime value (CLV)**, and cohort retention.

### 3.3 Role-Playing Date Dimensions
`dw.fact_sales` references `dw.dim_date` through three distinct foreign key roles:
1. `purchase_date_key`: When the customer checked out.
2. `delivered_date_key`: When the carrier handed the package to the customer (nullable for shipped/canceled orders).
3. `estimated_date_key`: The SLA promised delivery deadline.

### 3.4 Idempotency & Re-Run Safety
1. **Dimensions (`04_load_dimensions.sql`)**: Uses `MERGE ... WHEN MATCHED THEN UPDATE ... WHEN NOT MATCHED THEN INSERT`. Re-running does not produce duplicate surrogate keys.
2. **Facts (`05_load_facts.sql`)**: Uses `INSERT ... WHERE NOT EXISTS (SELECT 1 FROM dw.fact_sales WHERE order_id = oi.order_id AND order_item_id = oi.order_item_id)`. Re-running does not create duplicate transactions.
3. **Staging Ingestion**: Truncated prior to every reload (`TRUNCATE TABLE staging.stg_*`).

### 3.5 Bulk Ingestion Performance
- Staging loads leverage SQLAlchemy with `mssql+pyodbc` and `fast_executemany=True`.
- Inserts are executed in batches of `5,000` rows, reducing network round-trips from minutes to seconds.
