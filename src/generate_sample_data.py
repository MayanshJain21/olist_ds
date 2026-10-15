"""Synthetic sample data generator for the Olist dataset.

Generates 50 realistic orders across all 9 Olist tables matching Kaggle schemas.
Enables local execution, validation, and testing without requiring real Kaggle credentials.
"""

from datetime import datetime, timedelta
from pathlib import Path
import random
from typing import Dict
import uuid

import pandas as pd

from config.settings import settings
from src.utils import logger


def generate_sample_dataset(
    target_dir: Path = settings.RAW_DATA_DIR,
    num_orders: int = 50,
    seed: int = 42,
) -> Dict[str, pd.DataFrame]:
    """Generates synthetic sample data matching the 9 Olist Kaggle CSV files.

    Args:
        target_dir: Destination directory for the generated CSV files.
        num_orders: Number of synthetic orders to create (default 50).
        seed: Random seed for deterministic generation.

    Returns:
        Dict[str, pd.DataFrame]: Dictionary mapping table name to generated DataFrame.
    """
    random.seed(seed)
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Generating %d synthetic sample orders in %s...", num_orders, target_dir)

    # 1. Geolocation & Brazilian Cities
    locations = [
        {"zip": "01310", "lat": -23.5630, "lng": -46.6543, "city": "sao paulo", "state": "SP"},
        {"zip": "01311", "lat": -23.5650, "lng": -46.6510, "city": "sao paulo", "state": "SP"},
        {"zip": "20040", "lat": -22.9068, "lng": -43.1729, "city": "rio de janeiro", "state": "RJ"},
        {"zip": "20041", "lat": -22.9080, "lng": -43.1750, "city": "rio de janeiro", "state": "RJ"},
        {"zip": "30140", "lat": -19.9320, "lng": -43.9380, "city": "belo horizonte", "state": "MG"},
        {"zip": "80010", "lat": -25.4290, "lng": -49.2710, "city": "curitiba", "state": "PR"},
        {"zip": "90010", "lat": -30.0330, "lng": -51.2300, "city": "porto alegre", "state": "RS"},
        {"zip": "70040", "lat": -15.7938, "lng": -47.8827, "city": "brasilia", "state": "DF"},
        {"zip": "40020", "lat": -12.9714, "lng": -38.5014, "city": "salvador", "state": "BA"},
        {"zip": "50030", "lat": -8.0578, "lng": -34.8829, "city": "recife", "state": "PE"},
    ]

    # Geolocation table has multiple records per zip prefix
    geo_records = []
    for loc in locations:
        for _ in range(3):
            geo_records.append(
                {
                    "geolocation_zip_code_prefix": loc["zip"],
                    "geolocation_lat": loc["lat"] + random.uniform(-0.01, 0.01),
                    "geolocation_lng": loc["lng"] + random.uniform(-0.01, 0.01),
                    "geolocation_city": loc["city"],
                    "geolocation_state": loc["state"],
                }
            )
    df_geolocation = pd.DataFrame(geo_records)

    # 2. Category Translations
    categories = [
        ("beleza_saude", "health_beauty"),
        ("informatica_acessorios", "computers_accessories"),
        ("cama_mesa_banho", "bed_bath_table"),
        ("esporte_lazer", "sports_leisure"),
        ("moveis_decoracao", "furniture_decor"),
        ("telefonia", "telephony"),
        ("utilidades_domesticas", "housewares"),
        ("relogios_presentes", "watches_gifts"),
        ("automotivo", "auto"),
        ("brinquedos", "toys"),
    ]
    df_translation = pd.DataFrame(categories, columns=["product_category_name", "product_category_name_english"])

    # 3. Products (20 products)
    product_records = []
    product_ids = [uuid.uuid4().hex for _ in range(20)]
    for pid in product_ids:
        cat_pair = random.choice(categories)
        product_records.append(
            {
                "product_id": pid,
                "product_category_name": cat_pair[0],
                "product_name_lenght": random.randint(30, 60),  # intentional Kaggle spelling
                "product_description_lenght": random.randint(150, 1500),
                "product_photos_qty": random.randint(1, 6),
                "product_weight_g": random.randint(200, 5000),
                "product_length_cm": random.randint(15, 60),
                "product_height_cm": random.randint(10, 40),
                "product_width_cm": random.randint(10, 50),
            }
        )
    # Add one product with missing category to test "unknown" fill
    product_records.append(
        {
            "product_id": uuid.uuid4().hex,
            "product_category_name": None,
            "product_name_lenght": 40,
            "product_description_lenght": 200,
            "product_photos_qty": 1,
            "product_weight_g": 500,
            "product_length_cm": 20,
            "product_height_cm": 10,
            "product_width_cm": 15,
        }
    )
    product_ids.append(product_records[-1]["product_id"])
    df_products = pd.DataFrame(product_records)

    # 4. Sellers (10 sellers)
    seller_records = []
    seller_ids = [uuid.uuid4().hex for _ in range(10)]
    for sid in seller_ids:
        loc = random.choice(locations)
        seller_records.append(
            {
                "seller_id": sid,
                "seller_zip_code_prefix": loc["zip"],
                "seller_city": loc["city"],
                "seller_state": loc["state"],
            }
        )
    df_sellers = pd.DataFrame(seller_records)

    # 5. Customers (40 unique customers, 50 order-level customer_ids to demonstrate repeat buyers)
    customer_unique_ids = [uuid.uuid4().hex for _ in range(35)]
    customer_records = []
    order_customer_ids = []

    for i in range(num_orders):
        cid = uuid.uuid4().hex
        order_customer_ids.append(cid)
        # 15 orders reuse customer_unique_ids to create repeat customers
        uniq_id = customer_unique_ids[i % len(customer_unique_ids)]
        loc = random.choice(locations)
        customer_records.append(
            {
                "customer_id": cid,
                "customer_unique_id": uniq_id,
                "customer_zip_code_prefix": loc["zip"],
                "customer_city": loc["city"],
                "customer_state": loc["state"],
            }
        )
    df_customers = pd.DataFrame(customer_records)

    # 6. Orders, Items, Payments, Reviews
    order_records = []
    item_records = []
    payment_records = []
    review_records = []

    base_time = datetime(2017, 1, 15, 10, 0, 0)

    for i, cid in enumerate(order_customer_ids):
        oid = uuid.uuid4().hex
        purchase_time = base_time + timedelta(days=i * 12, hours=random.randint(1, 20), minutes=random.randint(1, 59))
        approved_time = purchase_time + timedelta(hours=random.randint(1, 12))
        carrier_time = approved_time + timedelta(days=random.randint(1, 3))
        estimated_time = purchase_time + timedelta(days=random.randint(14, 25))

        # Most delivered, a few shipped or canceled
        if i == 0:
            status = "shipped"
            delivered_time = None
        elif i == 1:
            status = "canceled"
            delivered_time = None
            carrier_time = None
            approved_time = None
        else:
            status = "delivered"
            # Some delivered before estimate, some after (delayed)
            delay_factor = random.choice([-5, -3, -1, 0, 2, 6])
            delivered_time = estimated_time + timedelta(days=delay_factor, hours=random.randint(1, 8))

        order_records.append(
            {
                "order_id": oid,
                "customer_id": cid,
                "order_status": status,
                "order_purchase_timestamp": purchase_time.strftime("%Y-%m-%d %H:%M:%S"),
                "order_approved_at": approved_time.strftime("%Y-%m-%d %H:%M:%S") if approved_time else None,
                "order_delivered_carrier_date": carrier_time.strftime("%Y-%m-%d %H:%M:%S") if carrier_time else None,
                "order_delivered_customer_date": delivered_time.strftime("%Y-%m-%d %H:%M:%S") if delivered_time else None,
                "order_estimated_delivery_date": estimated_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        # 1 to 3 items per order
        num_items = 1 if i % 4 != 0 else random.randint(2, 3)
        order_total_price = 0.0
        order_total_freight = 0.0

        for item_idx in range(1, num_items + 1):
            pid = random.choice(product_ids)
            sid = random.choice(seller_ids)
            price = round(random.uniform(19.90, 499.00), 2)
            freight = round(random.uniform(10.00, 45.00), 2)
            order_total_price += price
            order_total_freight += freight

            item_records.append(
                {
                    "order_id": oid,
                    "order_item_id": item_idx,
                    "product_id": pid,
                    "seller_id": sid,
                    "shipping_limit_date": (purchase_time + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
                    "price": price,
                    "freight_value": freight,
                }
            )

        # Payments: 1 or 2 payments
        total_order_val = round(order_total_price + order_total_freight, 2)
        if random.random() < 0.2:
            # Split payment: voucher + credit card
            v_val = round(min(30.0, total_order_val / 2.0), 2)
            cc_val = round(total_order_val - v_val, 2)
            payment_records.append(
                {
                    "order_id": oid,
                    "payment_sequential": 1,
                    "payment_type": "voucher",
                    "payment_installments": 1,
                    "payment_value": v_val,
                }
            )
            payment_records.append(
                {
                    "order_id": oid,
                    "payment_sequential": 2,
                    "payment_type": "credit_card",
                    "payment_installments": random.choice([1, 2, 3, 6]),
                    "payment_value": cc_val,
                }
            )
        else:
            ptype = random.choice(["credit_card", "boleto", "credit_card"])
            payment_records.append(
                {
                    "order_id": oid,
                    "payment_sequential": 1,
                    "payment_type": ptype,
                    "payment_installments": random.choice([1, 2, 4, 10]) if ptype == "credit_card" else 1,
                    "payment_value": total_order_val,
                }
            )

        # Reviews: 1 review per order (plus an updated second review on one order to test latest selection)
        review_time = (delivered_time or estimated_time) + timedelta(days=1)
        score = random.choices([1, 2, 3, 4, 5], weights=[0.05, 0.05, 0.1, 0.3, 0.5])[0]
        review_records.append(
            {
                "review_id": uuid.uuid4().hex,
                "order_id": oid,
                "review_score": score,
                "review_comment_title": f"Review title for order {i+1}",
                "review_comment_message": "Produto excelente e entrega pontual." if score >= 4 else "Demorou a chegar.",
                "review_creation_date": review_time.strftime("%Y-%m-%d 00:00:00"),
                "review_answer_timestamp": (review_time + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    # Add duplicate review on order 0 to test keep latest
    first_order_id = order_records[0]["order_id"]
    review_records.append(
        {
            "review_id": uuid.uuid4().hex,
            "order_id": first_order_id,
            "review_score": 5,
            "review_comment_title": "Atualização de avaliação",
            "review_comment_message": "Problema resolvido com suporte ágil.",
            "review_creation_date": datetime(2017, 2, 1, 0, 0, 0).strftime("%Y-%m-%d 00:00:00"),
            "review_answer_timestamp": datetime(2017, 2, 1, 15, 30, 0).strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    df_orders = pd.DataFrame(order_records)
    df_order_items = pd.DataFrame(item_records)
    df_payments = pd.DataFrame(payment_records)
    df_reviews = pd.DataFrame(review_records)

    datasets = {
        "orders": (df_orders, settings.RAW_TABLE_FILES["orders"]),
        "order_items": (df_order_items, settings.RAW_TABLE_FILES["order_items"]),
        "order_payments": (df_payments, settings.RAW_TABLE_FILES["order_payments"]),
        "order_reviews": (df_reviews, settings.RAW_TABLE_FILES["order_reviews"]),
        "products": (df_products, settings.RAW_TABLE_FILES["products"]),
        "customers": (df_customers, settings.RAW_TABLE_FILES["customers"]),
        "sellers": (df_sellers, settings.RAW_TABLE_FILES["sellers"]),
        "geolocation": (df_geolocation, settings.RAW_TABLE_FILES["geolocation"]),
        "category_translation": (df_translation, settings.RAW_TABLE_FILES["category_translation"]),
    }

    result_dfs = {}
    for table_name, (df, filename) in datasets.items():
        file_path = target_dir / filename
        df.to_csv(file_path, index=False, encoding="utf-8")
        result_dfs[table_name] = df
        logger.info("Saved %s (%d rows) to %s", table_name, len(df), file_path)

    logger.info("Successfully generated all 9 synthetic Olist sample CSVs.")
    return result_dfs


if __name__ == "__main__":
    generate_sample_dataset()
