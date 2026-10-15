"""Data cleaning and transformation module.

Implements business rules for the Olist dataset:
- orders: timestamp parsing, deduplication, derived delivery_days & delay_days
- products: typo correction (lenght -> length), category translation join, unknown fill
- reviews: keep latest review per order_id
- geolocation: aggregate to one row per zip prefix (mean coords, first city/state)
- customers, sellers, order_items, payments: deduplication
- outputs Parquet files to local disk and optionally uploads to Azure Blob Storage
"""

from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config.settings import settings
from src.utils import logger


def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans the orders dataset.

    - Parses all 5 timestamp columns with errors="coerce"
    - Drops duplicate order_id
    - Derives delivery_days (delivered - purchase) and delay_days (delivered - estimated)

    Args:
        df: Raw orders DataFrame.

    Returns:
        pd.DataFrame: Cleaned orders DataFrame.
    """
    df_clean = df.copy()

    timestamp_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]

    for col in timestamp_cols:
        if col in df_clean.columns:
            df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")

    # Drop duplicate order_id
    initial_rows = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=["order_id"])
    dropped_dupes = initial_rows - len(df_clean)
    if dropped_dupes > 0:
        logger.info("clean_orders: dropped %d duplicate order_id rows.", dropped_dupes)

    # Derive delivery_days: delivered to customer - purchase timestamp (in float days)
    if "order_delivered_customer_date" in df_clean.columns and "order_purchase_timestamp" in df_clean.columns:
        delivery_diff = df_clean["order_delivered_customer_date"] - df_clean["order_purchase_timestamp"]
        df_clean["delivery_days"] = (delivery_diff.dt.total_seconds() / 86400.0).round(2)
    else:
        df_clean["delivery_days"] = None

    # Derive delay_days: delivered to customer - estimated delivery date (in float days)
    # Positive means late, negative means arrived ahead of schedule
    if "order_delivered_customer_date" in df_clean.columns and "order_estimated_delivery_date" in df_clean.columns:
        delay_diff = df_clean["order_delivered_customer_date"] - df_clean["order_estimated_delivery_date"]
        df_clean["delay_days"] = (delay_diff.dt.total_seconds() / 86400.0).round(2)
    else:
        df_clean["delay_days"] = None

    return df_clean


def clean_products(df: pd.DataFrame, translation_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Cleans the products dataset.

    - Renames misspelled columns: product_name_lenght -> product_name_length,
      product_description_lenght -> product_description_length
    - Left joins category translations on product_category_name
    - Fills missing product categories with "unknown"

    Args:
        df: Raw products DataFrame.
        translation_df: Optional category translation DataFrame.

    Returns:
        pd.DataFrame: Cleaned products DataFrame.
    """
    df_clean = df.copy()

    # Rename misspelled Kaggle columns
    rename_map = {
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    }
    df_clean = df_clean.rename(columns=rename_map)

    # Join category translations if available
    if translation_df is not None and not translation_df.empty:
        trans_clean = translation_df.copy().drop_duplicates(subset=["product_category_name"])
        # Ensure destination doesn't already have the english col
        if "product_category_name_english" in df_clean.columns:
            df_clean = df_clean.drop(columns=["product_category_name_english"])

        df_clean = df_clean.merge(
            trans_clean[["product_category_name", "product_category_name_english"]],
            on="product_category_name",
            how="left",
        )
    elif "product_category_name_english" not in df_clean.columns:
        df_clean["product_category_name_english"] = "unknown"

    # Fill missing categories with "unknown"
    df_clean["product_category_name"] = df_clean["product_category_name"].fillna("unknown")
    df_clean["product_category_name_english"] = df_clean["product_category_name_english"].fillna("unknown")

    # Drop exact duplicate rows
    df_clean = df_clean.drop_duplicates()
    return df_clean


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans the reviews dataset.

    - Parses timestamps with errors="coerce"
    - Keeps only the latest review per order_id (sorted by review_answer_timestamp)

    Args:
        df: Raw reviews DataFrame.

    Returns:
        pd.DataFrame: Cleaned reviews DataFrame.
    """
    df_clean = df.copy()

    for col in ["review_creation_date", "review_answer_timestamp"]:
        if col in df_clean.columns:
            df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")

    # Keep only the latest review per order_id
    if "review_answer_timestamp" in df_clean.columns:
        df_clean = df_clean.sort_values(by="review_answer_timestamp", ascending=True, na_position="first")
    df_clean = df_clean.drop_duplicates(subset=["order_id"], keep="last")

    return df_clean


def clean_geolocation(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans the geolocation dataset.

    - Aggregates to one row per zip prefix: mean lat/lng, first city/state

    Args:
        df: Raw geolocation DataFrame.

    Returns:
        pd.DataFrame: Cleaned geolocation DataFrame.
    """
    df_clean = df.copy()

    # Drop exact duplicates before aggregation
    df_clean = df_clean.drop_duplicates()

    # Aggregate to one row per zip code prefix
    grouped = (
        df_clean.groupby("geolocation_zip_code_prefix")
        .agg(
            geolocation_lat=("geolocation_lat", "mean"),
            geolocation_lng=("geolocation_lng", "mean"),
            geolocation_city=("geolocation_city", "first"),
            geolocation_state=("geolocation_state", "first"),
        )
        .reset_index()
    )

    return grouped


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans customers dataset by dropping exact duplicates."""
    return df.copy().drop_duplicates()


def clean_sellers(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans sellers dataset by dropping exact duplicates."""
    return df.copy().drop_duplicates()


def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans order_items dataset by dropping exact duplicates and validating data types."""
    df_clean = df.copy().drop_duplicates()
    if "shipping_limit_date" in df_clean.columns:
        df_clean["shipping_limit_date"] = pd.to_datetime(df_clean["shipping_limit_date"], errors="coerce")
    if "price" in df_clean.columns:
        df_clean["price"] = pd.to_numeric(df_clean["price"], errors="coerce")
    if "freight_value" in df_clean.columns:
        df_clean["freight_value"] = pd.to_numeric(df_clean["freight_value"], errors="coerce")
    return df_clean


def clean_payments(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans payments dataset by dropping exact duplicates."""
    df_clean = df.copy().drop_duplicates()
    if "payment_value" in df_clean.columns:
        df_clean["payment_value"] = pd.to_numeric(df_clean["payment_value"], errors="coerce")
    return df_clean


def clean_all(
    raw_dir: Path = settings.RAW_DATA_DIR,
    processed_dir: Path = settings.PROCESSED_DATA_DIR,
    upload_to_azure: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Orchestrates cleaning of all raw Olist datasets and writes Parquet files.

    Args:
        raw_dir: Directory containing raw CSV files.
        processed_dir: Destination directory for cleaned Parquet files.
        upload_to_azure: Whether to upload Parquet files to Azure Blob Storage 'processed' container.

    Returns:
        Dict[str, pd.DataFrame]: Dictionary mapping table name to cleaned DataFrame.
    """
    logger.info("Starting cleaning pipeline from %s -> %s...", raw_dir, processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load raw files
    raw_dfs: Dict[str, pd.DataFrame] = {}
    for table_key, filename in settings.RAW_TABLE_FILES.items():
        file_path = raw_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(
                f"Missing required raw CSV file: {file_path}. "
                "Ensure Kaggle datasets are downloaded or run generate_sample_data.py."
            )
        raw_dfs[table_key] = pd.read_csv(file_path)
        logger.info("Loaded raw %s (%d rows)", table_key, len(raw_dfs[table_key]))

    # 2. Apply cleaning rules
    cleaned: Dict[str, pd.DataFrame] = {}

    cleaned["orders"] = clean_orders(raw_dfs["orders"])
    cleaned["products"] = clean_products(raw_dfs["products"], raw_dfs.get("category_translation"))
    cleaned["reviews"] = clean_reviews(raw_dfs["order_reviews"])
    cleaned["geolocation"] = clean_geolocation(raw_dfs["geolocation"])
    cleaned["customers"] = clean_customers(raw_dfs["customers"])
    cleaned["sellers"] = clean_sellers(raw_dfs["sellers"])
    cleaned["order_items"] = clean_order_items(raw_dfs["order_items"])
    cleaned["payments"] = clean_payments(raw_dfs["order_payments"])

    # 3. Save to Parquet format
    for table_name, df_clean in cleaned.items():
        parquet_file = processed_dir / f"{table_name}.parquet"
        df_clean.to_parquet(parquet_file, index=False, engine="pyarrow")
        logger.info("Written %s (%d rows) to Parquet: %s", table_name, len(df_clean), parquet_file)

    # 4. Optional Azure upload
    if upload_to_azure:
        if not settings.AZURE_STORAGE_CONNECTION_STRING:
            logger.warning("Azure Storage connection string not set. Skipping Azure processed upload.")
        else:
            from src.ingest import AzureBlobIngestor

            logger.info("Uploading cleaned Parquet files to Azure container '%s'...", settings.AZURE_CONTAINER_PROCESSED)
            ingestor = AzureBlobIngestor(container_name=settings.AZURE_CONTAINER_PROCESSED)
            ingestor.ensure_container_exists()
            for table_name in cleaned.keys():
                parquet_file = processed_dir / f"{table_name}.parquet"
                ingestor.upload_file(parquet_file, blob_name=parquet_file.name)
            logger.info("Successfully uploaded all Parquet files to Azure container '%s'.", settings.AZURE_CONTAINER_PROCESSED)

    logger.info("Cleaning pipeline finished successfully.")
    return cleaned


if __name__ == "__main__":
    clean_all()
