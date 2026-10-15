"""Unit tests for src/validate.py data quality validation checks using in-memory DataFrames."""

import pandas as pd
import pytest

from src.validate import DataValidationError, validate_dataset


@pytest.fixture
def valid_dataset():
    """Provides a minimal, fully valid in-memory dataset passing all 7 checks."""
    df_orders = pd.DataFrame(
        [
            {
                "order_id": "ord_101",
                "customer_id": "cust_101",
                "order_status": "delivered",
                "order_purchase_timestamp": pd.Timestamp("2017-06-01 10:00:00"),
                "order_delivered_customer_date": pd.Timestamp("2017-06-05 10:00:00"),
                "order_estimated_delivery_date": pd.Timestamp("2017-06-10 10:00:00"),
            },
            {
                "order_id": "ord_102",
                "customer_id": "cust_102",
                "order_status": "delivered",
                "order_purchase_timestamp": pd.Timestamp("2017-06-02 12:00:00"),
                "order_delivered_customer_date": pd.Timestamp("2017-06-08 15:00:00"),
                "order_estimated_delivery_date": pd.Timestamp("2017-06-12 10:00:00"),
            },
        ]
    )

    df_items = pd.DataFrame(
        [
            {
                "order_id": "ord_101",
                "order_item_id": 1,
                "product_id": "prod_1",
                "seller_id": "sell_1",
                "price": 99.90,
                "freight_value": 15.00,
            },
            {
                "order_id": "ord_102",
                "order_item_id": 1,
                "product_id": "prod_2",
                "seller_id": "sell_1",
                "price": 149.00,
                "freight_value": 20.00,
            },
        ]
    )

    df_products = pd.DataFrame(
        [
            {"product_id": "prod_1", "product_category_name": "beleza_saude", "product_category_name_english": "health_beauty"},
            {"product_id": "prod_2", "product_category_name": "telefonia", "product_category_name_english": "telephony"},
        ]
    )

    df_sellers = pd.DataFrame(
        [
            {"seller_id": "sell_1", "seller_zip_code_prefix": "01310", "seller_city": "sao paulo", "seller_state": "SP"}
        ]
    )

    df_reviews = pd.DataFrame(
        [
            {"review_id": "r1", "order_id": "ord_101", "review_score": 5},
            {"review_id": "r2", "order_id": "ord_102", "review_score": 4},
        ]
    )

    df_customers = pd.DataFrame(
        [
            {"customer_id": "cust_101", "customer_unique_id": "uniq_1", "customer_state": "SP"},
            {"customer_id": "cust_102", "customer_unique_id": "uniq_2", "customer_state": "RJ"},
        ]
    )

    df_payments = pd.DataFrame(
        [
            {"order_id": "ord_101", "payment_sequential": 1, "payment_type": "credit_card", "payment_value": 114.90},
            {"order_id": "ord_102", "payment_sequential": 1, "payment_type": "boleto", "payment_value": 169.00},
        ]
    )

    return {
        "orders": df_orders,
        "order_items": df_items,
        "products": df_products,
        "sellers": df_sellers,
        "reviews": df_reviews,
        "customers": df_customers,
        "payments": df_payments,
    }


def test_validate_dataset_success(valid_dataset):
    """Tests that a fully conforming dataset passes all validation checks."""
    result = validate_dataset(valid_dataset)
    assert result["status"] == "PASSED"
    assert result["failed_checks"] == 0
    assert result["total_checks"] == 7
    assert "orders" in result["row_counts"]


def test_validate_duplicate_order_id_fails(valid_dataset):
    """Tests failure when duplicate order_id exists in orders."""
    dupe_row = valid_dataset["orders"].iloc[0:1].copy()
    valid_dataset["orders"] = pd.concat([valid_dataset["orders"], dupe_row], ignore_index=True)

    with pytest.raises(DataValidationError) as exc_info:
        validate_dataset(valid_dataset)

    assert any("duplicate order_id" in err for err in exc_info.value.errors)


def test_validate_null_purchase_timestamp_fails(valid_dataset):
    """Tests failure when order_purchase_timestamp contains null values."""
    valid_dataset["orders"].loc[0, "order_purchase_timestamp"] = None

    with pytest.raises(DataValidationError) as exc_info:
        validate_dataset(valid_dataset)

    assert any("null or unparseable order_purchase_timestamp" in err for err in exc_info.value.errors)


def test_validate_negative_price_or_freight_fails(valid_dataset):
    """Tests failure when price or freight_value is negative."""
    valid_dataset["order_items"].loc[0, "price"] = -10.0
    valid_dataset["order_items"].loc[1, "freight_value"] = -5.0

    with pytest.raises(DataValidationError) as exc_info:
        validate_dataset(valid_dataset)

    assert any("negative price" in err for err in exc_info.value.errors)
    assert any("negative freight_value" in err for err in exc_info.value.errors)


def test_validate_referential_integrity_orphaned_orders_fails(valid_dataset):
    """Tests failure when order_items references an order_id not in orders."""
    valid_dataset["order_items"].loc[0, "order_id"] = "non_existent_order_id"

    with pytest.raises(DataValidationError) as exc_info:
        validate_dataset(valid_dataset)

    assert any("not found in orders table" in err for err in exc_info.value.errors)


def test_validate_referential_integrity_orphaned_products_fails(valid_dataset):
    """Tests failure when order_items references a product_id not in products."""
    valid_dataset["order_items"].loc[0, "product_id"] = "non_existent_product_id"

    with pytest.raises(DataValidationError) as exc_info:
        validate_dataset(valid_dataset)

    assert any("not found in products table" in err for err in exc_info.value.errors)


def test_validate_referential_integrity_orphaned_sellers_fails(valid_dataset):
    """Tests failure when order_items references a seller_id not in sellers."""
    valid_dataset["order_items"].loc[0, "seller_id"] = "non_existent_seller_id"

    with pytest.raises(DataValidationError) as exc_info:
        validate_dataset(valid_dataset)

    assert any("not found in sellers table" in err for err in exc_info.value.errors)


def test_validate_invalid_review_score_fails(valid_dataset):
    """Tests failure when review_score is out of [1, 5] range."""
    valid_dataset["reviews"].loc[0, "review_score"] = 6  # Score > 5
    valid_dataset["reviews"].loc[1, "review_score"] = 0  # Score < 1

    with pytest.raises(DataValidationError) as exc_info:
        validate_dataset(valid_dataset)

    assert any("out-of-range" in err for err in exc_info.value.errors)


def test_validate_collects_all_errors_together(valid_dataset):
    """Tests that validation does NOT stop at the first error, but collects ALL failures."""
    # Inject 3 distinct errors
    valid_dataset["orders"].loc[0, "order_purchase_timestamp"] = None
    valid_dataset["order_items"].loc[0, "price"] = -50.0
    valid_dataset["reviews"].loc[0, "review_score"] = 99

    with pytest.raises(DataValidationError) as exc_info:
        validate_dataset(valid_dataset)

    # All 3 errors must be collected in the exception's errors list
    errors = exc_info.value.errors
    assert len(errors) >= 3
    assert any("null or unparseable order_purchase_timestamp" in err for err in errors)
    assert any("negative price" in err for err in errors)
    assert any("out-of-range" in err for err in errors)
