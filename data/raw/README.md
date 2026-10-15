# Raw Dataset Instructions

To run the pipeline with the full production dataset:

1. Download the Brazilian E-Commerce Public Dataset by Olist from Kaggle:
   **[Kaggle: Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)**

2. Extract the archive and place all 9 CSV files directly in this directory (`data/raw/`):
   - `olist_orders_dataset.csv`
   - `olist_order_items_dataset.csv`
   - `olist_order_payments_dataset.csv`
   - `olist_order_reviews_dataset.csv`
   - `olist_products_dataset.csv`
   - `olist_customers_dataset.csv`
   - `olist_sellers_dataset.csv`
   - `olist_geolocation_dataset.csv`
   - `product_category_name_translation.csv`

3. If you want to test the pipeline immediately without downloading the full dataset from Kaggle, run:
   ```bash
   python -m src.run_pipeline --local-only --generate-sample
   ```
   This will automatically populate synthetic sample datasets matching the exact Olist schemas.
