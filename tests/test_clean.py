"""Unit tests for src/clean.py data cleaning functions using in-memory DataFrames."""

import numpy as np
import pandas as pd
import pytest

from src.clean import (
    clean_customers,
    clean_geolocation,
    clean_order_items,
    clean_orders,
    clean_payments,
    clean_products,
    clean_reviews,
    clean_sellers,
)


def test_clean_orders_timestamp_parsing_and_deduplication():
    """Tests that orders cleaning parses 5 timestamps, drops duplicate order_ids, and derives days."""
    raw_orders = pd.DataFrame(
        [
            {
                "order_id": "ord_1",
                "customer_id": "cust_1",
                "order_status": "delivered",
                "order_purchase_timestamp": "2017-02-01 10:00:00",
                "order_approved_at": "2017-02-01 11:00:00",
                "order_delivered_carrier_date": "2017-02-03 14:00:00",
                "order_delivered_customer_date": "2017-02-06 10:00:00",  # 5 days after purchase
                "order_estimated_delivery_date": "2017-02-08 00:00:00",  # delivered ~1.58 days before estimated
            },
            {  # Duplicate order_id (should be dropped)
                "order_id": "ord_1",
                "customer_id": "cust_1",
                "order_status": "delivered",
                "order_purchase_timestamp": "2017-02-01 10:00:00",
                "order_approved_at": "2017-02-01 11:00:00",
                "order_delivered_carrier_date": "2017-02-03 14:00:00",
                "order_delivered_customer_date": "2017-02-06 10:00:00",
                "order_estimated_delivery_date": "2017-02-08 00:00:00",
            },
            {  # Shipped order (null delivered customer date)
                "order_id": "ord_2",
                "customer_id": "cust_2",
                "order_status": "shipped",
                "order_purchase_timestamp": "2017-03-01 12:00:00",
                "order_approved_at": "2017-03-01 13:00:00",
                "order_delivered_carrier_date": "2017-03-02 10:00:00",
                "order_delivered_customer_date": None,
                "order_estimated_delivery_date": "2017-03-15 00:00:00",
            },
            {  # Delayed order (delivered after estimated)
                "order_id": "ord_3",
                "customer_id": "cust_3",
                "order_status": "delivered",
                "order_purchase_timestamp": "2017-04-01 10:00:00",
                "order_approved_at": "2017-04-01 11:00:00",
                "order_delivered_carrier_date": "2017-04-02 10:00:00",
                "order_delivered_customer_date": "2017-04-20 10:00:00",
                "order_estimated_delivery_date": "2017-04-15 10:00:00",  # 5 days late
            },
        ]
    )

    cleaned = clean_orders(raw_orders)

    # 1. Deduplication check: 4 rows reduced to 3
    assert len(cleaned) == 3
    assert cleaned["order_id"].tolist() == ["ord_1", "ord_2", "ord_3"]

    # 2. Timestamp type checks
    for col in [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]:
        assert pd.api.types.is_datetime64_any_dtype(cleaned[col])

    # 3. Derived metrics check for ord_1 (delivered exactly 5 days after purchase)
    row_1 = cleaned[cleaned["order_id"] == "ord_1"].iloc[0]
    assert row_1["delivery_days"] == pytest.approx(5.0, abs=0.01)
    # Delivered before estimated: delay_days should be negative
    assert row_1["delay_days"] < 0

    # 4. Null check for ord_2 (not delivered yet)
    row_2 = cleaned[cleaned["order_id"] == "ord_2"].iloc[0]
    assert np.isnan(row_2["delivery_days"]) or row_2["delivery_days"] is None
    assert np.isnan(row_2["delay_days"]) or row_2["delay_days"] is None

    # 5. Delayed check for ord_3 (delivered 5 days after estimated date)
    row_3 = cleaned[cleaned["order_id"] == "ord_3"].iloc[0]
    assert row_3["delay_days"] == pytest.approx(5.0, abs=0.01)


def test_clean_products_renaming_translation_and_unknown_fill():
    """Tests products cleaning for column spelling fixes, category translation, and fallback fill."""
    raw_products = pd.DataFrame(
        [
            {
                "product_id": "p1",
                "product_category_name": "beleza_saude",
                "product_name_lenght": 50,  # Intentional Kaggle typo
                "product_description_lenght": 300,
                "product_photos_qty": 2,
                "product_weight_g": 500,
            },
            {
                "product_id": "p2",
                "product_category_name": None,  # Missing category
                "product_name_lenght": 40,
                "product_description_lenght": 200,
                "product_photos_qty": 1,
                "product_weight_g": 300,
            },
            {
                "product_id": "p3",
                "product_category_name": "categoria_sem_traducao",  # Untranslated category
                "product_name_lenght": 35,
                "product_description_lenght": 150,
                "product_photos_qty": 3,
                "product_weight_g": 800,
            },
        ]
    )

    translation_df = pd.DataFrame(
        [
            {"product_category_name": "beleza_saude", "product_category_name_english": "health_beauty"},
        ]
    )

    cleaned = clean_products(raw_products, translation_df=translation_df)

    # 1. Column renaming check
    assert "product_name_length" in cleaned.columns
    assert "product_description_length" in cleaned.columns
    assert "product_name_lenght" not in cleaned.columns
    assert "product_description_lenght" not in cleaned.columns

    # 2. Translated category check
    p1 = cleaned[cleaned["product_id"] == "p1"].iloc[0]
    assert p1["product_category_name"] == "beleza_saude"
    assert p1["product_category_name_english"] == "health_beauty"

    # 3. Missing category fallback check
    p2 = cleaned[cleaned["product_id"] == "p2"].iloc[0]
    assert p2["product_category_name"] == "unknown"
    assert p2["product_category_name_english"] == "unknown"

    # 4. Untranslated category fallback check
    p3 = cleaned[cleaned["product_id"] == "p3"].iloc[0]
    assert p3["product_category_name"] == "categoria_sem_traducao"
    assert p3["product_category_name_english"] == "unknown"


def test_clean_reviews_keeps_latest_review_per_order():
    """Tests reviews cleaning keeps only the latest review per order_id by review_answer_timestamp."""
    raw_reviews = pd.DataFrame(
        [
            {
                "review_id": "rev_old",
                "order_id": "ord_1",
                "review_score": 2,
                "review_creation_date": "2017-05-01 00:00:00",
                "review_answer_timestamp": "2017-05-02 10:00:00",
            },
            {
                "review_id": "rev_new",
                "order_id": "ord_1",
                "review_score": 5,
                "review_creation_date": "2017-05-05 00:00:00",
                "review_answer_timestamp": "2017-05-06 14:00:00",  # Newer answer timestamp
            },
            {
                "review_id": "rev_other",
                "order_id": "ord_2",
                "review_score": 4,
                "review_creation_date": "2017-06-01 00:00:00",
                "review_answer_timestamp": "2017-06-02 09:00:00",
            },
        ]
    )

    cleaned = clean_reviews(raw_reviews)

    assert len(cleaned) == 2
    # ord_1 should retain only rev_new with review_score 5
    ord_1_rev = cleaned[cleaned["order_id"] == "ord_1"].iloc[0]
    assert ord_1_rev["review_id"] == "rev_new"
    assert ord_1_rev["review_score"] == 5


def test_clean_geolocation_aggregates_to_one_row_per_zip():
    """Tests geolocation aggregation to one row per zip prefix with mean coordinates and first city/state."""
    raw_geo = pd.DataFrame(
        [
            {
                "geolocation_zip_code_prefix": "01310",
                "geolocation_lat": -23.50,
                "geolocation_lng": -46.60,
                "geolocation_city": "sao paulo",
                "geolocation_state": "SP",
            },
            {
                "geolocation_zip_code_prefix": "01310",
                "geolocation_lat": -23.60,
                "geolocation_lng": -46.70,
                "geolocation_city": "são paulo",
                "geolocation_state": "SP",
            },
            {
                "geolocation_zip_code_prefix": "20040",
                "geolocation_lat": -22.90,
                "geolocation_lng": -43.10,
                "geolocation_city": "rio de janeiro",
                "geolocation_state": "RJ",
            },
        ]
    )

    cleaned = clean_geolocation(raw_geo)

    assert len(cleaned) == 2
    row_sp = cleaned[cleaned["geolocation_zip_code_prefix"] == "01310"].iloc[0]
    # Mean lat: (-23.50 + -23.60) / 2 = -23.55
    assert row_sp["geolocation_lat"] == pytest.approx(-23.55, abs=0.001)
    # Mean lng: (-46.60 + -46.70) / 2 = -46.65
    assert row_sp["geolocation_lng"] == pytest.approx(-46.65, abs=0.001)
    assert row_sp["geolocation_city"] == "sao paulo"
    assert row_sp["geolocation_state"] == "SP"


def test_clean_exact_duplicates():
    """Tests that customers, sellers, order_items, and payments drop exact duplicates."""
    df_with_dupes = pd.DataFrame(
        [
            {"id": "A", "val": 10},
            {"id": "A", "val": 10},  # Duplicate
            {"id": "B", "val": 20},
        ]
    )

    assert len(clean_customers(df_with_dupes)) == 2
    assert len(clean_sellers(df_with_dupes)) == 2
    assert len(clean_payments(df_with_dupes)) == 2

    # Order items also parses price/freight
    df_items = pd.DataFrame(
        [
            {"order_id": "o1", "order_item_id": 1, "price": "29.90", "freight_value": "10.00"},
            {"order_id": "o1", "order_item_id": 1, "price": "29.90", "freight_value": "10.00"},
        ]
    )
    cleaned_items = clean_order_items(df_items)
    assert len(cleaned_items) == 1
    assert cleaned_items["price"].dtype in [np.float64, float]
