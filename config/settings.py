"""Project settings and configuration loader.

Loads environment variables, defines filesystem paths, raw-to-staging table mappings,
and connection parameters for Azure Blob Storage and Azure SQL Database.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Dict, List, Optional
import urllib.parse
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


@dataclass
class Settings:
    """Central configuration class for the Olist Data Warehouse pipeline."""

    # Project filesystem paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data")
    RAW_DATA_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "raw")
    PROCESSED_DATA_DIR: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "processed"
    )
    SQL_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "sql")
    LOGS_DIR: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "logs")

    # Azure Blob Storage / ADLS Gen2
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    AZURE_CONTAINER_RAW: str = os.getenv("AZURE_CONTAINER_RAW", "raw")
    AZURE_CONTAINER_PROCESSED: str = os.getenv("AZURE_CONTAINER_PROCESSED", "processed")

    # Azure SQL Database
    AZURE_SQL_SERVER: Optional[str] = os.getenv("AZURE_SQL_SERVER")
    AZURE_SQL_DATABASE: str = os.getenv("AZURE_SQL_DATABASE", "olist_dw")
    AZURE_SQL_USER: Optional[str] = os.getenv("AZURE_SQL_USER")
    AZURE_SQL_PASSWORD: Optional[str] = os.getenv("AZURE_SQL_PASSWORD")
    AZURE_SQL_PORT: int = int(os.getenv("AZURE_SQL_PORT", "1433"))
    AZURE_SQL_DRIVER: str = os.getenv("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")

    # Pipeline Performance & Resiliency Settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "5000"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY_SECONDS: float = float(os.getenv("RETRY_DELAY_SECONDS", "2.0"))

    # Mapping of logical table keys to Kaggle CSV filenames
    RAW_TABLE_FILES: Dict[str, str] = field(
        default_factory=lambda: {
            "orders": "olist_orders_dataset.csv",
            "order_items": "olist_order_items_dataset.csv",
            "order_payments": "olist_order_payments_dataset.csv",
            "order_reviews": "olist_order_reviews_dataset.csv",
            "products": "olist_products_dataset.csv",
            "customers": "olist_customers_dataset.csv",
            "sellers": "olist_sellers_dataset.csv",
            "geolocation": "olist_geolocation_dataset.csv",
            "category_translation": "product_category_name_translation.csv",
        }
    )

    # Mapping of logical table keys to staging table names in Azure SQL
    STAGING_TABLES: Dict[str, str] = field(
        default_factory=lambda: {
            "orders": "stg_orders",
            "order_items": "stg_order_items",
            "order_payments": "stg_order_payments",
            "order_reviews": "stg_order_reviews",
            "products": "stg_products",
            "customers": "stg_customers",
            "sellers": "stg_sellers",
            "geolocation": "stg_geolocation",
        }
    )

    # Sequential SQL script execution list for DDL and ELT transformations
    SQL_SCRIPTS_ORDER: List[str] = field(
        default_factory=lambda: [
            "01_create_schemas.sql",
            "02_staging_tables.sql",
            "03_warehouse_tables.sql",
            "04_load_dimensions.sql",
            "05_load_facts.sql",
            "06_views.sql",
        ]
    )

    def get_sql_alchemy_url(self) -> str:
        """Constructs an ODBC connection string for SQLAlchemy to connect to Azure SQL.

        Returns:
            str: SQLAlchemy mssql+pyodbc connection URL.

        Raises:
            ValueError: If required Azure SQL parameters are missing.
        """
        if not self.AZURE_SQL_SERVER or not self.AZURE_SQL_USER or not self.AZURE_SQL_PASSWORD:
            raise ValueError(
                "Missing required Azure SQL configuration: AZURE_SQL_SERVER, "
                "AZURE_SQL_USER, and AZURE_SQL_PASSWORD must be set."
            )

        odbc_str = (
            f"DRIVER={{{self.AZURE_SQL_DRIVER}}};"
            f"SERVER={self.AZURE_SQL_SERVER},{self.AZURE_SQL_PORT};"
            f"DATABASE={self.AZURE_SQL_DATABASE};"
            f"UID={self.AZURE_SQL_USER};"
            f"PWD={self.AZURE_SQL_PASSWORD};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
            "Connection Timeout=30;"
        )
        params = urllib.parse.quote_plus(odbc_str)
        return f"mssql+pyodbc:///?odbc_connect={params}"

    def ensure_directories(self) -> None:
        """Ensures that all required local directories exist."""
        for directory in [self.RAW_DATA_DIR, self.PROCESSED_DATA_DIR, self.LOGS_DIR]:
            directory.mkdir(parents=True, exist_ok=True)


# Global singleton settings instance
settings = Settings()
settings.ensure_directories()
