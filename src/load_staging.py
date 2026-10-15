"""Staging data loader for Azure SQL Database.

Loads cleaned Parquet files into the 'staging' schema using SQLAlchemy with
fast_executemany=True and chunksize=5000 for high-throughput batch insertion.
"""

from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError

from config.settings import settings
from src.utils import logger, retry_operation


class StagingLoader:
    """Manages high-throughput ingestion from Parquet into Azure SQL staging tables."""

    def __init__(self, connection_url: Optional[str] = None, chunksize: int = settings.CHUNK_SIZE) -> None:
        """Initializes the StagingLoader.

        Args:
            connection_url: Optional SQLAlchemy connection URL override.
            chunksize: Batch size for fast_executemany inserts.
        """
        self.connection_url = connection_url
        self.chunksize = chunksize
        self._engine: Optional[Engine] = None

    def get_engine(self) -> Engine:
        """Instantiates and returns the SQLAlchemy Engine configured with fast_executemany.

        Returns:
            Engine: Configured SQLAlchemy Engine.

        Raises:
            ImportError: If pyodbc is not installed.
            ValueError: If connection parameters are missing.
        """
        if self._engine is None:
            try:
                import pyodbc  # noqa: F401
            except ImportError as err:
                raise ImportError(
                    "The 'pyodbc' package is required for connecting to Azure SQL Database. "
                    "Please install Microsoft ODBC Driver 18 for SQL Server and pip install pyodbc. "
                    "To run the pipeline locally without Azure SQL, pass the '--local-only' flag."
                ) from err

            url = self.connection_url or settings.get_sql_alchemy_url()
            logger.info("Initializing SQLAlchemy engine for Azure SQL Database...")
            self._engine = create_engine(
                url,
                fast_executemany=True,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
        return self._engine

    @retry_operation(
        max_attempts=settings.MAX_RETRIES,
        delay=settings.RETRY_DELAY_SECONDS,
        exceptions=(OperationalError, DBAPIError, ConnectionError, TimeoutError),
    )
    def load_table(self, df: pd.DataFrame, table_name: str, schema: str = "staging") -> int:
        """Loads a single DataFrame into the designated staging table with retry logic.

        Truncates the staging table first to ensure idempotent loading.

        Args:
            df: Data to load.
            table_name: Staging table name (e.g., 'stg_orders').
            schema: Database schema name (default 'staging').

        Returns:
            int: Number of rows successfully inserted.
        """
        engine = self.get_engine()
        full_table_name = f"{schema}.{table_name}"
        logger.info("Truncating and staging %d rows into [%s] (chunksize=%d)...", len(df), full_table_name, self.chunksize)

        with engine.begin() as conn:
            # Idempotently truncate the staging table before loading new batch
            conn.execute(text(f"TRUNCATE TABLE {schema}.{table_name};"))

            # Bulk insert using SQLAlchemy and fast_executemany
            df.to_sql(
                name=table_name,
                schema=schema,
                con=conn,
                if_exists="append",
                index=False,
                chunksize=self.chunksize,
                method=None,  # method=None leverages fast_executemany at pyodbc driver level
            )

        logger.info("Successfully loaded %d rows into [%s].", len(df), full_table_name)
        return len(df)

    def load_all_staging(
        self,
        processed_dir: Path = settings.PROCESSED_DATA_DIR,
        staging_mapping: Optional[Dict[str, str]] = None,
    ) -> Dict[str, int]:
        """Loads all cleaned Parquet files into corresponding staging tables.

        Args:
            processed_dir: Path to directory containing Parquet files.
            staging_mapping: Mapping of logical dataset names to staging table names.

        Returns:
            Dict[str, int]: Dictionary of staged row counts per table.
        """
        mapping = staging_mapping or settings.STAGING_TABLES
        staged_counts: Dict[str, int] = {}

        logger.info("Starting staging load for %d tables from %s...", len(mapping), processed_dir)

        for dataset_key, staging_table in mapping.items():
            parquet_path = processed_dir / f"{dataset_key}.parquet"
            if not parquet_path.exists():
                logger.warning("Processed file %s not found. Skipping staging table [%s].", parquet_path, staging_table)
                continue

            df = pd.read_parquet(parquet_path)
            rows_loaded = self.load_table(df, staging_table, schema="staging")
            staged_counts[staging_table] = rows_loaded

        logger.info("Staging load finished: %d tables loaded successfully.", len(staged_counts))
        return staged_counts


def load_staging_tables(
    processed_dir: Path = settings.PROCESSED_DATA_DIR,
    connection_url: Optional[str] = None,
) -> Dict[str, int]:
    """Convenience functional entry point for loading staging tables.

    Args:
        processed_dir: Path to directory containing Parquet files.
        connection_url: Optional connection URL override.

    Returns:
        Dict[str, int]: Staged row counts per table.
    """
    loader = StagingLoader(connection_url=connection_url)
    return loader.load_all_staging(processed_dir=processed_dir)


if __name__ == "__main__":
    load_staging_tables()
