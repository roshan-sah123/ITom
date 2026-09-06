"""Google Cloud Firestore Synchronization Service for ITOM Telemetry.

This module provides integration capabilities for synchronizing precomputed
dashboard summaries and endpoint records to Google Cloud Firestore or Firebase
Firestore databases. It supports both live Firestore cloud environments and
local offline/mock modes for deterministic testing and offline execution.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Optional import of google-cloud-firestore
try:
    from google.cloud import firestore  # type: ignore
    FIRESTORE_AVAILABLE = True
except ImportError:
    firestore = None  # type: ignore
    FIRESTORE_AVAILABLE = False


class FirestoreSyncService:
    """Service for synchronizing ITOM telemetry payloads and device collections to Firestore.

    Attributes:
        project_id: GCP project ID or Firebase project ID.
        collection_name: Firestore target collection name.
        credentials_path: Path to Google Service Account JSON credentials file.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
        collection_name: str = "itom_telemetry",
    ) -> None:
        """Initialize the Firestore synchronization service.

        Args:
            project_id: GCP / Firebase project ID.
            credentials_path: Optional filesystem path to Service Account JSON.
            collection_name: Default collection name in Firestore.
        """
        self.project_id = project_id or os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.collection_name = collection_name
        self._db: Any = None
        self._offline_cache: Dict[str, Any] = {}

        self._initialize_client()

    def _initialize_client(self) -> None:
        """Attempt to initialize the Google Cloud Firestore client if dependencies exist."""
        if not FIRESTORE_AVAILABLE:
            logger.info("Firestore SDK not installed in environment; operating in offline/mock mode.")
            return

        try:
            if self.credentials_path and os.path.exists(self.credentials_path):
                self._db = firestore.Client.from_service_account_json(
                    self.credentials_path,
                    project=self.project_id,
                )
            else:
                self._db = firestore.Client(project=self.project_id)
            logger.info("Firestore client initialized successfully for project '%s'.", self.project_id)
        except Exception as exc:
            logger.warning("Could not connect to Firestore client: %s. Falling back to offline mode.", exc)
            self._db = None

    def is_available(self) -> bool:
        """Check whether live Firestore database connection is active.

        Returns:
            True if connected to live Firestore, False if operating in offline mode.
        """
        return self._db is not None

    def sync_summary_payload(
        self,
        payload: Dict[str, Any],
        doc_id: str = "intune_summary",
    ) -> Dict[str, Any]:
        """Upload or update the precomputed dashboard summary document in Firestore.

        Args:
            payload: Precomputed summary payload matching `data/intune_summary.json` schema.
            doc_id: Document ID in the telemetry collection (defaults to 'intune_summary').

        Returns:
            Dictionary containing sync metadata and status.
        """
        sync_meta = {
            "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "doc_id": doc_id,
            "collection": self.collection_name,
            "status": "success",
            "offline_mode": not self.is_available(),
        }

        doc_data = {
            **payload,
            "_syncMetadata": sync_meta,
        }

        if self.is_available():
            try:
                doc_ref = self._db.collection(self.collection_name).document(doc_id)
                doc_ref.set(doc_data, merge=True)
                logger.info("Successfully synced summary payload to Firestore [%s/%s]", self.collection_name, doc_id)
            except Exception as exc:
                logger.error("Firestore sync failed: %s", exc)
                sync_meta["status"] = f"failed: {exc}"
                sync_meta["offline_mode"] = True
                self._offline_cache[doc_id] = doc_data
        else:
            self._offline_cache[doc_id] = doc_data
            logger.info("Cached summary payload offline [%s/%s]", self.collection_name, doc_id)

        return sync_meta

    def sync_device_batch(
        self,
        devices: List[Dict[str, Any]],
        collection_name: str = "intune_devices",
        batch_size: int = 500,
    ) -> int:
        """Sync a list of individual device documents in batches to Firestore.

        Args:
            devices: List of device dictionaries.
            collection_name: Target subcollection name for device records.
            batch_size: Maximum operations per batch commit (max 500 in Firestore).

        Returns:
            Number of successfully committed device documents.
        """
        if not devices:
            return 0

        if not self.is_available():
            logger.info("Offline mode: Simulated batch sync of %d devices to collection '%s'", len(devices), collection_name)
            return len(devices)

        committed_count = 0
        total_devices = len(devices)

        for i in range(0, total_devices, batch_size):
            chunk = devices[i : i + batch_size]
            batch = self._db.batch()
            for dev in chunk:
                dev_id = dev.get("id") or dev.get("serialNumber") or str(time.time())
                doc_ref = self._db.collection(collection_name).document(str(dev_id))
                batch.set(doc_ref, dev, merge=True)
            batch.commit()
            committed_count += len(chunk)
            logger.info("Committed batch: %d/%d devices to Firestore", committed_count, total_devices)

        return committed_count

    def get_latest_summary(self, doc_id: str = "intune_summary") -> Optional[Dict[str, Any]]:
        """Retrieve the latest summary payload from Firestore or offline cache.

        Args:
            doc_id: Document ID to retrieve.

        Returns:
            The summary payload dictionary, or None if not found.
        """
        if self.is_available():
            try:
                doc_ref = self._db.collection(self.collection_name).document(doc_id)
                snapshot = doc_ref.get()
                if snapshot.exists:
                    return snapshot.to_dict()
            except Exception as exc:
                logger.error("Failed to read from Firestore: %s", exc)

        return self._offline_cache.get(doc_id)

    def export_to_firestore_compatible_json(
        self,
        payload: Dict[str, Any],
        output_path: str,
    ) -> str:
        """Export payload to a JSON structure optimized for Firestore import/export tools.

        Args:
            payload: The dashboard summary payload.
            output_path: Filesystem path for the exported JSON file.

        Returns:
            The absolute path of the written file.
        """
        export_payload = {
            "collection": self.collection_name,
            "documents": [
                {
                    "id": "intune_summary",
                    "data": payload,
                    "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            ],
        }

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2)

        logger.info("Exported Firestore compatible JSON to: %s", output_path)
        return os.path.abspath(output_path)
