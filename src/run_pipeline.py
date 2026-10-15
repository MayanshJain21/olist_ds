"""Pipeline runner and CLI entry point.

Orchestrates the end-to-end data pipeline:
1. Ingest: uploads raw CSVs to Azure Blob Storage 'raw' container (skipped with --local-only)
2. Clean: cleans raw datasets, derives metrics, and outputs Parquet files
3. Validate: runs comprehensive data quality and referential integrity checks
4. Staging Load: bulk-loads Parquet into Azure SQL staging schema (skipped with --local-only)
5. Warehouse ELT: runs SQL DDL, dimension MERGEs, and fact loads (skipped with --local-only)
"""

import argparse
from pathlib import Path
import sys
import time
from typing import List, Optional

from config.settings import settings
from src.clean import clean_all
from src.generate_sample_data import generate_sample_dataset
from src.ingest import ingest_raw_data
from src.load_staging import load_staging_tables
from src.utils import logger
from src.validate import validate_processed_parquet


def execute_sql_file(engine, file_path: Path) -> None:
    """Executes a T-SQL script containing GO batch separators.

    Args:
        engine: SQLAlchemy Engine.
        file_path: Path to .sql file.
    """
    from sqlalchemy import text

    logger.info("Executing SQL script: %s...", file_path.name)
    with open(file_path, "r", encoding="utf-8") as f:
        script_content = f.read()

    # Split batches by GO (case insensitive, on its own line)
    batches = [
        batch.strip()
        for batch in script_content.split("GO")
        if batch.strip()
    ]

    with engine.connect() as conn:
        for idx, batch in enumerate(batches, start=1):
            if batch:
                logger.debug("Executing batch %d of %s", idx, file_path.name)
                conn.execute(text(batch))
                conn.commit()

    logger.info("Successfully executed: %s", file_path.name)


def run_pipeline(
    local_only: bool = False,
    generate_sample: bool = False,
    raw_dir: Path = settings.RAW_DATA_DIR,
    processed_dir: Path = settings.PROCESSED_DATA_DIR,
) -> bool:
    """Runs the full ELT pipeline with conditional local-only mode.

    Args:
        local_only: If True, skips Azure Blob upload and Azure SQL loading.
        generate_sample: If True or if raw_dir is empty, generates synthetic sample data.
        raw_dir: Directory containing raw CSV files.
        processed_dir: Directory for cleaned Parquet files.

    Returns:
        bool: True if pipeline succeeded.
    """
    start_total_time = time.time()
    logger.info("==================================================")
    logger.info("STARTING OLIST DATA WAREHOUSE PIPELINE")
    logger.info("Mode: %s", "LOCAL-ONLY (Offline)" if local_only else "FULL CLOUD (Azure Blob + Azure SQL)")
    logger.info("==================================================")

    # Step 0: Ensure data availability
    csv_files = list(raw_dir.glob("*.csv"))
    if generate_sample or not csv_files:
        logger.info("Raw data directory empty or sample generation requested. Generating synthetic sample dataset...")
        generate_sample_dataset(target_dir=raw_dir, num_orders=50)

    # Step 1: Ingestion to Azure Blob Storage (Raw Container)
    if not local_only:
        logger.info("\n>>> STAGE 1: Azure Blob Raw Ingestion")
        t0 = time.time()
        try:
            ingest_raw_data(raw_dir=raw_dir)
            logger.info("Stage 1 complete in %.2f seconds.", time.time() - t0)
        except Exception as exc:
            logger.error("Stage 1 failed: %s", exc)
            raise
    else:
        logger.info("\n>>> STAGE 1: Skipped Azure Blob Ingestion (--local-only specified).")

    # Step 2: Data Cleaning & Parquet Transformation
    logger.info("\n>>> STAGE 2: Data Cleaning & Parquet Transformation")
    t0 = time.time()
    try:
        clean_all(
            raw_dir=raw_dir,
            processed_dir=processed_dir,
            upload_to_azure=(not local_only),
        )
        logger.info("Stage 2 complete in %.2f seconds.", time.time() - t0)
    except Exception as exc:
        logger.error("Stage 2 cleaning failed: %s", exc)
        raise

    # Step 3: Data Quality Validation
    logger.info("\n>>> STAGE 3: Data Quality Validation")
    t0 = time.time()
    try:
        validation_report = validate_processed_parquet(processed_dir=processed_dir)
        logger.info("Stage 3 complete in %.2f seconds. Status: %s", time.time() - t0, validation_report["status"])
    except Exception as exc:
        logger.error("Stage 3 data validation failed: %s", exc)
        raise

    # Step 4 & 5: Azure SQL Staging & Warehouse Transformations
    if not local_only:
        logger.info("\n>>> STAGE 4: Azure SQL Staging Ingestion")
        t0 = time.time()
        try:
            from src.load_staging import StagingLoader

            loader = StagingLoader()
            engine = loader.get_engine()
            loader.load_all_staging(processed_dir=processed_dir)
            logger.info("Stage 4 complete in %.2f seconds.", time.time() - t0)
        except Exception as exc:
            logger.error("Stage 4 staging load failed: %s", exc)
            raise

        logger.info("\n>>> STAGE 5: SQL Warehouse Schemas, Dimensions, Facts & Views")
        t0 = time.time()
        try:
            for sql_script_name in settings.SQL_SCRIPTS_ORDER:
                script_path = settings.SQL_DIR / sql_script_name
                if not script_path.exists():
                    raise FileNotFoundError(f"SQL script not found: {script_path}")
                execute_sql_file(engine, script_path)
            logger.info("Stage 5 complete in %.2f seconds.", time.time() - t0)
        except Exception as exc:
            logger.error("Stage 5 SQL warehouse execution failed: %s", exc)
            raise
    else:
        logger.info("\n>>> STAGE 4 & 5: Skipped Azure SQL Staging & Warehouse Load (--local-only specified).")

    elapsed_total = time.time() - start_total_time
    logger.info("==================================================")
    logger.info("PIPELINE COMPLETED SUCCESSFULLY in %.2f seconds!", elapsed_total)
    logger.info("==================================================")
    return True


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="End-to-end Olist E-commerce Data Warehouse Pipeline (Azure Blob + Azure SQL + Python)"
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Run data cleaning and quality checks locally, skipping Azure upload and Azure SQL loading.",
    )
    parser.add_argument(
        "--generate-sample",
        action="store_true",
        help="Generate synthetic sample dataset (50 orders) before running pipeline.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=settings.RAW_DATA_DIR,
        help="Custom path to raw CSV directory.",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=settings.PROCESSED_DATA_DIR,
        help="Custom path to processed Parquet directory.",
    )
    return parser.parse_args(args)


def main() -> None:
    """Main CLI entrypoint."""
    args = parse_args()
    try:
        success = run_pipeline(
            local_only=args.local_only,
            generate_sample=args.generate_sample,
            raw_dir=args.raw_dir,
            processed_dir=args.processed_dir,
        )
        sys.exit(0 if success else 1)
    except Exception as exc:
        logger.error("Pipeline terminated with error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
