"""Data quality validation module.

Enforces business and referential integrity constraints across the cleaned datasets:
- no duplicate order_id in orders
- no null purchase timestamp
- no negative price or freight_value in order_items
- referential integrity: order_items.order_id in orders.order_id
- referential integrity: order_items.product_id in products.product_id
- referential integrity: order_items.seller_id in sellers.seller_id
- review_score in [1, 5]
- collects all errors, logs each, and raises DataValidationError if any fail.
- logs row counts for all tables.
"""

from pathlib import Path
from typing import Any, Dict, List, Set

import pandas as pd

from config.settings import settings
from src.utils import logger


class DataValidationError(Exception):
    """Exception raised when one or more data quality validation checks fail."""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        error_summary = "\n".join(f"  - [FAILED CHECK]: {err}" for err in errors)
        super().__init__(f"Data quality validation failed with {len(errors)} error(s):\n{error_summary}")


def validate_dataset(data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Validates cleaned DataFrames against data quality rules and referential integrity.

    Collects all validation errors, logs each individual failure, and raises
    DataValidationError if any checks fail.

    Args:
        data: Dictionary mapping table name to DataFrame.

    Returns:
        Dict[str, Any]: Validation summary report containing row counts and pass statuses.

    Raises:
        DataValidationError: If any data quality checks fail.
    """
    logger.info("==================================================")
    logger.info("STARTING DATA QUALITY VALIDATION")
    logger.info("==================================================")

    # 1. Log row counts per table
    row_counts: Dict[str, int] = {}
    for table_name, df in data.items():
        count = len(df)
        row_counts[table_name] = count
        logger.info("Table [%-15s]: %d rows, %d columns", table_name, count, len(df.columns))

    errors: List[str] = []

    # --------------------------------------------------------------------------
    # Check 1: No duplicate order_id in orders
    # --------------------------------------------------------------------------
    df_orders = data.get("orders")
    if df_orders is not None:
        dupe_orders = df_orders["order_id"].duplicated().sum()
        if dupe_orders > 0:
            err = f"orders table contains {dupe_orders} duplicate order_id value(s)."
            errors.append(err)
        else:
            logger.info("PASS: orders table has unique order_id values.")
    else:
        errors.append("orders table is missing from dataset.")

    # --------------------------------------------------------------------------
    # Check 2: No null order_purchase_timestamp in orders
    # --------------------------------------------------------------------------
    if df_orders is not None:
        null_purchases = df_orders["order_purchase_timestamp"].isna().sum()
        if null_purchases > 0:
            err = f"orders table contains {null_purchases} null or unparseable order_purchase_timestamp value(s)."
            errors.append(err)
        else:
            logger.info("PASS: orders table has no null purchase timestamps.")

    # --------------------------------------------------------------------------
    # Check 3: No negative price or freight_value in order_items
    # --------------------------------------------------------------------------
    df_items = data.get("order_items")
    if df_items is not None:
        if "price" in df_items.columns:
            negative_prices = (df_items["price"] < 0).sum()
            if negative_prices > 0:
                err = f"order_items table contains {negative_prices} negative price value(s) (min: {df_items['price'].min()})."
                errors.append(err)
            else:
                logger.info("PASS: order_items table has no negative prices.")

        if "freight_value" in df_items.columns:
            negative_freight = (df_items["freight_value"] < 0).sum()
            if negative_freight > 0:
                err = f"order_items table contains {negative_freight} negative freight_value value(s) (min: {df_items['freight_value'].min()})."
                errors.append(err)
            else:
                logger.info("PASS: order_items table has no negative freight values.")
    else:
        errors.append("order_items table is missing from dataset.")

    # --------------------------------------------------------------------------
    # Check 4: Every order_items.order_id exists in orders
    # --------------------------------------------------------------------------
    if df_items is not None and df_orders is not None:
        valid_order_ids: Set[str] = set(df_orders["order_id"].dropna())
        item_order_ids: Set[str] = set(df_items["order_id"].dropna())
        orphaned_orders = item_order_ids - valid_order_ids
        if orphaned_orders:
            err = f"order_items contains {len(orphaned_orders)} order_id value(s) not found in orders table."
            errors.append(err)
        else:
            logger.info("PASS: Referential integrity satisfied: all order_items.order_id exist in orders.")

    # --------------------------------------------------------------------------
    # Check 5: Every order_items.product_id exists in products
    # --------------------------------------------------------------------------
    df_products = data.get("products")
    if df_items is not None and df_products is not None:
        valid_product_ids: Set[str] = set(df_products["product_id"].dropna())
        item_product_ids: Set[str] = set(df_items["product_id"].dropna())
        orphaned_products = item_product_ids - valid_product_ids
        if orphaned_products:
            err = f"order_items contains {len(orphaned_products)} product_id value(s) not found in products table."
            errors.append(err)
        else:
            logger.info("PASS: Referential integrity satisfied: all order_items.product_id exist in products.")
    elif df_products is None:
        errors.append("products table is missing from dataset.")

    # --------------------------------------------------------------------------
    # Check 6: Every order_items.seller_id exists in sellers
    # --------------------------------------------------------------------------
    df_sellers = data.get("sellers")
    if df_items is not None and df_sellers is not None:
        valid_seller_ids: Set[str] = set(df_sellers["seller_id"].dropna())
        item_seller_ids: Set[str] = set(df_items["seller_id"].dropna())
        orphaned_sellers = item_seller_ids - valid_seller_ids
        if orphaned_sellers:
            err = f"order_items contains {len(orphaned_sellers)} seller_id value(s) not found in sellers table."
            errors.append(err)
        else:
            logger.info("PASS: Referential integrity satisfied: all order_items.seller_id exist in sellers.")
    elif df_sellers is None:
        errors.append("sellers table is missing from dataset.")

    # --------------------------------------------------------------------------
    # Check 7: review_score between 1 and 5 in reviews
    # --------------------------------------------------------------------------
    df_reviews = data.get("reviews")
    if df_reviews is not None:
        if "review_score" in df_reviews.columns:
            invalid_scores = ((df_reviews["review_score"] < 1) | (df_reviews["review_score"] > 5)).sum()
            null_scores = df_reviews["review_score"].isna().sum()
            if invalid_scores > 0 or null_scores > 0:
                err = f"reviews table contains {invalid_scores} out-of-range (<1 or >5) and {null_scores} null review_score(s)."
                errors.append(err)
            else:
                logger.info("PASS: All review_score values are valid integers between 1 and 5.")
    else:
        errors.append("reviews table is missing from dataset.")

    # --------------------------------------------------------------------------
    # Error evaluation
    # --------------------------------------------------------------------------
    if errors:
        logger.error("Data quality validation completed with %d error(s):", len(errors))
        for idx, err in enumerate(errors, start=1):
            logger.error("  [%d] %s", idx, err)
        raise DataValidationError(errors)

    logger.info("==================================================")
    logger.info("ALL DATA QUALITY CHECKS PASSED (7/7 checks passed)")
    logger.info("==================================================")

    return {
        "status": "PASSED",
        "total_checks": 7,
        "failed_checks": 0,
        "row_counts": row_counts,
    }


def validate_processed_parquet(processed_dir: Path = settings.PROCESSED_DATA_DIR) -> Dict[str, Any]:
    """Loads Parquet files from disk and validates them.

    Args:
        processed_dir: Directory containing cleaned Parquet files.

    Returns:
        Dict[str, Any]: Validation summary report.
    """
    logger.info("Loading Parquet files from %s for validation...", processed_dir)
    tables = ["orders", "order_items", "payments", "reviews", "products", "customers", "sellers", "geolocation"]
    data: Dict[str, pd.DataFrame] = {}

    for table in tables:
        parquet_file = processed_dir / f"{table}.parquet"
        if not parquet_file.exists():
            raise FileNotFoundError(f"Missing processed Parquet file: {parquet_file}")
        data[table] = pd.read_parquet(parquet_file)

    return validate_dataset(data)


if __name__ == "__main__":
    validate_processed_parquet()
