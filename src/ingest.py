"""Raw data ingestion module.

Uploads raw CSV files from local disk to Azure Blob Storage / ADLS Gen2 'raw' container.
Includes exponential backoff retry logic and connection verification.
"""

from pathlib import Path
from typing import Dict, List, Optional
import os

from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError

from config.settings import settings
from src.utils import logger, retry_operation


class AzureBlobIngestor:
    """Handles ingestion of raw datasets into Azure Blob Storage."""

    def __init__(self, connection_string: Optional[str] = None, container_name: Optional[str] = None) -> None:
        """Initializes the Azure Blob Ingestor.

        Args:
            connection_string: Azure Storage connection string.
            container_name: Target container name (defaults to settings.AZURE_CONTAINER_RAW).
        """
        self.connection_string = connection_string or settings.AZURE_STORAGE_CONNECTION_STRING
        self.container_name = container_name or settings.AZURE_CONTAINER_RAW
        self._blob_service_client: Optional[BlobServiceClient] = None

    def get_service_client(self) -> BlobServiceClient:
        """Lazily instantiates and returns the BlobServiceClient.

        Returns:
            BlobServiceClient: Authenticated Azure Blob Service Client.

        Raises:
            ValueError: If connection string is not provided.
        """
        if not self._blob_service_client:
            if not self.connection_string:
                raise ValueError(
                    "Azure Storage connection string is missing. "
                    "Set AZURE_STORAGE_CONNECTION_STRING in your .env file or environment."
                )
            self._blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        return self._blob_service_client

    def ensure_container_exists(self) -> None:
        """Ensures the target blob container exists, creating it if necessary."""
        client = self.get_service_client()
        container_client = client.get_container_client(self.container_name)
        if not container_client.exists():
            logger.info("Container '%s' does not exist. Creating container...", self.container_name)
            container_client.create_container()
            logger.info("Container '%s' created successfully.", self.container_name)
        else:
            logger.debug("Container '%s' verified.", self.container_name)

    @retry_operation(
        max_attempts=settings.MAX_RETRIES,
        delay=settings.RETRY_DELAY_SECONDS,
        exceptions=(AzureError, ConnectionError, TimeoutError),
    )
    def upload_file(self, local_file_path: Path, blob_name: Optional[str] = None) -> str:
        """Uploads a single local file to the Azure Blob container with retry logic.

        Args:
            local_file_path: Path to the local file to upload.
            blob_name: Name of the destination blob in the container.

        Returns:
            str: URL of the uploaded blob.
        """
        if not local_file_path.exists():
            raise FileNotFoundError(f"Local file does not exist: {local_file_path}")

        target_blob_name = blob_name or local_file_path.name
        client = self.get_service_client()
        blob_client = client.get_blob_client(container=self.container_name, blob=target_blob_name)

        logger.info("Uploading %s to container '%s' as blob '%s'...", local_file_path.name, self.container_name, target_blob_name)

        with open(local_file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

        logger.info("Successfully uploaded blob '%s' (size: %d bytes).", target_blob_name, local_file_path.stat().st_size)
        return blob_client.url

    def upload_raw_directory(
        self,
        raw_dir: Path = settings.RAW_DATA_DIR,
        table_files: Optional[Dict[str, str]] = None,
    ) -> List[str]:
        """Uploads all configured raw dataset CSV files to the Azure 'raw' container.

        Args:
            raw_dir: Path to directory containing raw CSV files.
            table_files: Mapping of table names to CSV filenames.

        Returns:
            List[str]: URLs of the uploaded blobs.
        """
        self.ensure_container_exists()
        files_to_upload = table_files or settings.RAW_TABLE_FILES
        uploaded_urls: List[str] = []

        logger.info("Starting batch upload of %d raw files from %s...", len(files_to_upload), raw_dir)

        for table_key, filename in files_to_upload.items():
            file_path = raw_dir / filename
            if not file_path.exists():
                logger.warning("Raw file '%s' for table '%s' not found. Skipping.", filename, table_key)
                continue

            url = self.upload_file(file_path, blob_name=filename)
            uploaded_urls.append(url)

        logger.info("Completed raw ingestion batch: %d files uploaded to container '%s'.", len(uploaded_urls), self.container_name)
        return uploaded_urls


def ingest_raw_data(
    raw_dir: Path = settings.RAW_DATA_DIR,
    connection_string: Optional[str] = None,
    container_name: Optional[str] = None,
) -> List[str]:
    """Convenience functional entry point for uploading raw CSVs to Azure.

    Args:
        raw_dir: Directory containing raw CSV files.
        connection_string: Optional connection string override.
        container_name: Target container name.

    Returns:
        List[str]: List of uploaded blob URLs.
    """
    ingestor = AzureBlobIngestor(connection_string=connection_string, container_name=container_name)
    return ingestor.upload_raw_directory(raw_dir=raw_dir)


if __name__ == "__main__":
    ingest_raw_data()
