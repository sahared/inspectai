"""
Cloud Storage Service
Manages file uploads (evidence photos, reports) to Google Cloud Storage.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "inspectai-evidence")
USE_MEMORY_STORE = os.getenv("USE_MEMORY_STORE", "false").lower() == "true"


class StorageService:
    """
    Handles Google Cloud Storage operations.
    Falls back to local filesystem for development.
    """

    def __init__(self):
        if USE_MEMORY_STORE:
            logger.info("Using local filesystem for storage")
            self.client = None
            self.bucket = None
            self._local_dir = os.path.join(os.getcwd(), "local_storage")
            os.makedirs(self._local_dir, exist_ok=True)
        else:
            try:
                from google.cloud import storage
                self.client = storage.Client()
                self.bucket = self.client.bucket(BUCKET_NAME)
                self._local_dir = None
                logger.info(f"Cloud Storage initialized with bucket: {BUCKET_NAME}")
            except Exception as e:
                logger.warning(
                    f"Cloud Storage unavailable ({e}), using local filesystem"
                )
                self.client = None
                self.bucket = None
                self._local_dir = os.path.join(os.getcwd(), "local_storage")
                os.makedirs(self._local_dir, exist_ok=True)

    async def upload_file(
        self,
        data: bytes,
        destination_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload a file to Cloud Storage.
        
        Returns the public URL or local path.
        """
        if self.bucket:
            blob = self.bucket.blob(destination_path)
            blob.upload_from_string(data, content_type=content_type)
            # Make publicly readable (for demo purposes)
            blob.make_public()
            url = blob.public_url
            logger.info(f"Uploaded to GCS: {destination_path}")
            return url
        else:
            # Save locally
            local_path = os.path.join(self._local_dir, destination_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(data)
            logger.info(f"Saved locally: {local_path}")
            return f"/local_storage/{destination_path}"

    async def upload_evidence_photo(
        self, session_id: str, evidence_number: int, image_data: bytes
    ) -> str:
        """Upload an evidence photo."""
        path = f"sessions/{session_id}/evidence/photo_{evidence_number}.jpg"
        return await self.upload_file(image_data, path, "image/jpeg")

    async def upload_report(self, session_id: str, report_data: bytes) -> str:
        """Upload a generated report PDF."""
        path = f"sessions/{session_id}/reports/inspection_report.pdf"
        return await self.upload_file(report_data, path, "application/pdf")

    async def get_download_url(self, path: str) -> Optional[str]:
        """Get a download URL for a file."""
        if self.bucket:
            blob = self.bucket.blob(path)
            if blob.exists():
                return blob.public_url
        elif self._local_dir:
            local_path = os.path.join(self._local_dir, path)
            if os.path.exists(local_path):
                return f"/local_storage/{path}"
        return None
