"""Microsoft Graph API Client for Intune Telemetry Ingestion.

This module provides a robust, production-grade client for authenticating
against Azure Active Directory (Azure AD / Microsoft Entra ID) using OAuth 2.0
Client Credentials Grant and extracting managed endpoint telemetry from the
Microsoft Graph API (`/deviceManagement/managedDevices`).
"""

import json
import logging
import os
import time
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Default Graph API endpoint configuration
DEFAULT_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
DEFAULT_MANAGED_DEVICES_ENDPOINT = f"{DEFAULT_GRAPH_BASE_URL}/deviceManagement/managedDevices"
DEFAULT_LOGIN_BASE_URL = "https://login.microsoftonline.com"

DEFAULT_SELECT_FIELDS = [
    "id",
    "deviceName",
    "operatingSystem",
    "osVersion",
    "complianceState",
    "userPrincipalName",
    "model",
    "manufacturer",
    "serialNumber",
    "lastSyncDateTime",
    "totalStorageSpaceInBytes",
    "freeStorageSpaceInBytes",
]


class GraphAuthError(Exception):
    """Raised when Azure AD authentication fails."""
    pass


class GraphApiError(Exception):
    """Raised when Microsoft Graph API requests fail."""
    pass


class GraphClient:
    """Enterprise Microsoft Graph API client for Intune telemetry ingestion.

    Handles OAuth 2.0 client credential token acquisition, token expiration caching,
    exponential backoff retry strategies for HTTP rate limits (429/503), and
    OData paginated collection streaming.

    Attributes:
        tenant_id: Azure AD tenant identifier GUID or domain.
        client_id: Registered Azure AD application client identifier.
        client_secret: Client secret associated with the application registration.
        scope: Microsoft Graph OAuth scope (defaults to 'https://graph.microsoft.com/.default').
    """

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        scope: str = "https://graph.microsoft.com/.default",
        timeout: int = 30,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        """Initialize the Microsoft Graph API client.

        Args:
            tenant_id: Azure AD tenant identifier (defaults to env AZURE_TENANT_ID).
            client_id: Azure AD client ID (defaults to env AZURE_CLIENT_ID).
            client_secret: Azure AD client secret (defaults to env AZURE_CLIENT_SECRET).
            scope: OAuth scope string.
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum number of retry attempts on transient network/rate errors.
            backoff_factor: Exponential backoff factor for retries.
        """
        self.tenant_id = tenant_id if tenant_id is not None else os.getenv("AZURE_TENANT_ID", "")
        self.client_id = client_id if client_id is not None else os.getenv("AZURE_CLIENT_ID", "")
        self.client_secret = client_secret if client_secret is not None else os.getenv("AZURE_CLIENT_SECRET", "")
        self.scope = scope
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._session: requests.Session = self._create_resilient_session()

    def _create_resilient_session(self) -> requests.Session:
        """Create a requests Session configured with automatic retry strategy.

        Returns:
            Configured `requests.Session` instance.
        """
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Acquire an OAuth 2.0 access token via Client Credentials Grant.

        Utilizes in-memory token caching with a 60-second buffer before expiration.

        Args:
            force_refresh: If True, bypasses token cache and requests a fresh token.

        Returns:
            Bearer access token string.

        Raises:
            GraphAuthError: If authentication request fails or required credentials are missing.
        """
        now = time.time()
        if not force_refresh and self._access_token and now < (self._token_expires_at - 60):
            return self._access_token

        if not self.tenant_id or not self.client_id or not self.client_secret:
            raise GraphAuthError(
                "Missing Azure AD credentials. Please provide tenant_id, client_id, "
                "and client_secret or set AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET env variables."
            )

        token_url = f"{DEFAULT_LOGIN_BASE_URL}/{self.tenant_id}/oauth2/v2.0/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
            "grant_type": "client_credentials",
        }

        logger.info("Requesting OAuth client-credentials token from Microsoft Entra.")
        try:
            response = self._session.post(token_url, headers=headers, data=payload, timeout=self.timeout)
            if response.status_code != 200:
                error_details = "Token endpoint rejected authentication"
                logger.error("OAuth token request failed (%d): %s", response.status_code, error_details)
                raise GraphAuthError(f"OAuth authentication failed ({response.status_code}): {error_details}")

            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3599)
            self._token_expires_at = now + float(expires_in)
            logger.info("Acquired fresh access token (expires in %ds).", expires_in)
            return self._access_token
        except requests.RequestException as exc:
            raise GraphAuthError(f"Entra connection failed ({type(exc).__name__})") from exc

    def fetch_managed_devices(
        self,
        select_fields: Optional[List[str]] = None,
        top: int = 100,
        max_devices: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch managed devices from Microsoft Intune via Microsoft Graph API.

        Handles OData pagination through `@odata.nextLink` until all records
        or `max_devices` are retrieved.

        Args:
            select_fields: List of Intune device attribute names to query.
            top: OData `$top` page size (default 100).
            max_devices: Optional limit on total devices to fetch.

        Returns:
            List of device dictionary records.

        Raises:
            GraphApiError: If Microsoft Graph API returns an error response.
        """
        token = self.get_access_token()
        fields = select_fields or DEFAULT_SELECT_FIELDS
        query_params = f"?$select={','.join(fields)}&$top={top}"
        endpoint: Optional[str] = f"{DEFAULT_MANAGED_DEVICES_ENDPOINT}{query_params}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "ConsistencyLevel": "eventual",
        }

        devices: List[Dict[str, Any]] = []
        page_num = 1
        visited = set()

        logger.info("Initiating Intune managed devices extraction from Microsoft Graph...")
        while endpoint:
            parsed = urlparse(endpoint)
            if parsed.scheme != "https" or parsed.hostname != "graph.microsoft.com" or endpoint in visited:
                raise GraphApiError("Invalid or repeated Graph pagination URL")
            visited.add(endpoint)
            try:
                response = self._session.get(endpoint, headers=headers, timeout=self.timeout)
                if response.status_code == 401:
                    # Token might have expired mid-pagination; refresh and retry once
                    logger.warning("Received 401 Unauthorized; refreshing token and retrying...")
                    token = self.get_access_token(force_refresh=True)
                    headers["Authorization"] = f"Bearer {token}"
                    response = self._session.get(endpoint, headers=headers, timeout=self.timeout)

                if response.status_code != 200:
                    error_msg = f"Graph API request failed on page {page_num} (HTTP {response.status_code})"
                    logger.error(error_msg)
                    raise GraphApiError(error_msg)

                page_data = response.json()
                if not isinstance(page_data, dict) or not isinstance(page_data.get("value"), list):
                    raise GraphApiError("Malformed Graph page: expected a value array")
                page_items = page_data["value"]
                devices.extend(page_items)
                logger.info("Page %d: fetched %d devices (total so far: %d)", page_num, len(page_items), len(devices))

                if max_devices and len(devices) >= max_devices:
                    devices = devices[:max_devices]
                    break

                endpoint = page_data.get("@odata.nextLink")
                page_num += 1
            except requests.RequestException as exc:
                raise GraphApiError(f"Graph page {page_num} connection failed ({type(exc).__name__})") from exc

        logger.info("Extraction complete. Total devices fetched: %d", len(devices))
        return devices

    def fetch_and_save(
        self,
        output_path: str,
        select_fields: Optional[List[str]] = None,
        max_devices: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch managed devices and save raw extraction payload to a JSON file.

        Args:
            output_path: Target filesystem path for the output JSON file.
            select_fields: Optional list of fields to select.
            max_devices: Optional limit on total records.

        Returns:
            The normalized raw telemetry payload dictionary.
        """
        devices = self.fetch_managed_devices(select_fields=select_fields, max_devices=max_devices)

        # Compute summary breakdown from raw records
        os_breakdown: Dict[str, int] = {}
        compliance_breakdown: Dict[str, int] = {}

        for dev in devices:
            os_name = dev.get("operatingSystem") or ""
            comp_state = dev.get("complianceState") or "unknown"
            os_breakdown[os_name] = os_breakdown.get(os_name, 0) + 1
            compliance_breakdown[comp_state] = compliance_breakdown.get(comp_state, 0) + 1

        raw_payload = {
            "summary": {
                "total_devices": len(devices),
                "os_breakdown": os_breakdown,
                "compliance_breakdown": compliance_breakdown,
            },
            "devices": devices,
        }

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(raw_payload, f, indent=4)

        logger.info("Saved raw Intune telemetry (%d devices) to %s", len(devices), output_path)
        return raw_payload
