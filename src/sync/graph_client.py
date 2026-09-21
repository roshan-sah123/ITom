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
from typing import Any, Dict, List, Optional
from urllib.parse import quote
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

        logger.info("Requesting OAuth 2.0 token from Azure AD: %s", token_url)
        try:
            response = self._session.post(token_url, headers=headers, data=payload, timeout=self.timeout)
            if response.status_code != 200:
                error_details = response.text
                logger.error("OAuth token request failed (%d): %s", response.status_code, error_details)
                raise GraphAuthError(f"OAuth authentication failed ({response.status_code}): {error_details}")

            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3599)
            self._token_expires_at = now + float(expires_in)
            logger.info("Acquired fresh access token (expires in %ds).", expires_in)
            return self._access_token
        except requests.RequestException as exc:
            logger.error("Network error during Azure AD authentication: %s", exc)
            raise GraphAuthError(f"Network error during authentication: {exc}") from exc

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

        logger.info("Initiating Intune managed devices extraction from Microsoft Graph...")
        while endpoint:
            try:
                response = self._session.get(endpoint, headers=headers, timeout=self.timeout)
                if response.status_code == 401:
                    # Token might have expired mid-pagination; refresh and retry once
                    logger.warning("Received 401 Unauthorized; refreshing token and retrying...")
                    token = self.get_access_token(force_refresh=True)
                    headers["Authorization"] = f"Bearer {token}"
                    response = self._session.get(endpoint, headers=headers, timeout=self.timeout)

                if response.status_code != 200:
                    error_msg = f"Graph API request failed on page {page_num} ({response.status_code}): {response.text}"
                    logger.error(error_msg)
                    raise GraphApiError(error_msg)

                page_data = response.json()
                page_items = page_data.get("value", [])
                devices.extend(page_items)
                logger.info("Page %d: fetched %d devices (total so far: %d)", page_num, len(page_items), len(devices))

                if max_devices and len(devices) >= max_devices:
                    devices = devices[:max_devices]
                    break

                endpoint = page_data.get("@odata.nextLink")
                page_num += 1
            except requests.RequestException as exc:
                logger.error("Network error while querying Graph API on page %d: %s", page_num, exc)
                raise GraphApiError(f"Network error during device extraction: {exc}") from exc

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

    def get_device_compliance_policy_states(self, managed_device_id: str) -> Dict[str, Any]:
        """Retrieve on-demand policy and setting evidence for one Intune device.

        This is deliberately not part of the full fleet sync. Policy settings are
        retrieved only after an operator selects a device to investigate.
        """
        token = self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        device_id = quote(str(managed_device_id), safe="")
        graph_bases = [DEFAULT_GRAPH_BASE_URL, "https://graph.microsoft.com/beta"]
        policies: Optional[List[Dict[str, Any]]] = None
        active_base = DEFAULT_GRAPH_BASE_URL

        for base_url in graph_bases:
            endpoint = f"{base_url}/deviceManagement/managedDevices/{device_id}/deviceCompliancePolicyStates"
            response = self._session.get(endpoint, headers=headers, timeout=self.timeout)
            if response.status_code == 404:
                continue
            if response.status_code != 200:
                raise GraphApiError(
                    f"Compliance policy state request failed ({response.status_code}): {response.text}"
                )
            payload = response.json()
            policies = list(payload.get("value", []))
            active_base = base_url
            break

        if policies is None:
            raise GraphApiError("Intune did not expose compliance policy states for this device.")

        normalized_policies: List[Dict[str, Any]] = []
        failed_setting_count = 0
        noncompliant_policy_count = 0
        for policy in policies:
            policy_id = str(policy.get("id") or "")
            policy_state = str(policy.get("state") or "unknown")
            setting_states = list(policy.get("settingStates") or [])

            # Some Graph responses omit nested setting states. Retrieve the
            # relationship separately so the dashboard retains actual evidence.
            if policy_id and not setting_states:
                setting_url = (
                    f"{active_base}/deviceManagement/managedDevices/{device_id}/"
                    f"deviceCompliancePolicyStates/{quote(policy_id, safe='')}/settingStates"
                )
                settings_response = self._session.get(setting_url, headers=headers, timeout=self.timeout)
                if settings_response.status_code == 200:
                    setting_states = list(settings_response.json().get("value", []))
                elif settings_response.status_code not in (404, 405):
                    raise GraphApiError(
                        f"Compliance setting state request failed ({settings_response.status_code}): "
                        f"{settings_response.text}"
                    )

            evidence = []
            for setting in setting_states:
                setting_state = str(setting.get("state") or "unknown")
                if setting_state.lower() not in ("compliant", "notapplicable"):
                    failed_setting_count += 1
                    evidence.append({
                        "setting_name": setting.get("settingName") or setting.get("setting") or "Unnamed setting",
                        "state": setting_state,
                    })

            if policy_state.lower() != "compliant":
                noncompliant_policy_count += 1
            normalized_policies.append({
                "policy_name": policy.get("displayName") or "Unnamed compliance policy",
                "policy_state": policy_state,
                "platform": policy.get("platformType") or "unknown",
                "settings": evidence,
            })

        return {
            "policies": normalized_policies,
            "noncompliant_policy_count": noncompliant_policy_count,
            "failing_setting_count": failed_setting_count,
            "graph_version": "beta" if active_base.endswith("/beta") else "v1.0",
        }

    def _get_graph_collection(self, endpoint: str) -> List[Dict[str, Any]]:
        """Retrieve every page of a Microsoft Graph collection for an on-demand view."""
        token = self.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        items: List[Dict[str, Any]] = []
        next_url: Optional[str] = endpoint

        while next_url:
            try:
                response = self._session.get(next_url, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                raise GraphApiError(f"Microsoft Graph collection request failed: {exc}") from exc
            if response.status_code != 200:
                raise GraphApiError(
                    f"Microsoft Graph collection request failed ({response.status_code}): {response.text}"
                )
            payload = response.json()
            items.extend(payload.get("value", []))
            next_url = payload.get("@odata.nextLink")

        return items

    def get_noncompliance_reason_summaries(self) -> List[Dict[str, Any]]:
        """Return the exact Intune compliance settings with reported device impact."""
        endpoint = (
            f"{DEFAULT_GRAPH_BASE_URL}/deviceManagement/"
            "deviceCompliancePolicySettingStateSummaries"
        )
        summaries = self._get_graph_collection(endpoint)
        reasons: List[Dict[str, Any]] = []

        for summary in summaries:
            noncompliant = int(summary.get("nonCompliantDeviceCount") or 0)
            errors = int(summary.get("errorDeviceCount") or 0)
            conflicts = int(summary.get("conflictDeviceCount") or 0)
            affected = noncompliant + errors + conflicts
            if not affected:
                continue
            reasons.append({
                "id": str(summary.get("id") or ""),
                "setting_name": summary.get("settingName") or summary.get("setting") or "Unnamed setting",
                "platform": summary.get("platformType") or "unknown",
                "noncompliant_count": noncompliant,
                "error_count": errors,
                "conflict_count": conflicts,
                "affected_count": affected,
            })

        return sorted(reasons, key=lambda item: (item["setting_name"].lower(), item["platform"].lower()))

    def get_noncompliant_devices_for_reason(self, summary_id: str) -> List[Dict[str, Any]]:
        """Return all non-compliant/error/conflict device states for one Intune setting."""
        endpoint = (
            f"{DEFAULT_GRAPH_BASE_URL}/deviceManagement/"
            f"deviceCompliancePolicySettingStateSummaries/{quote(str(summary_id), safe='')}/"
            "deviceComplianceSettingStates"
        )
        states = self._get_graph_collection(endpoint)
        affected_states = {"noncompliant", "error", "conflict"}
        devices: Dict[str, Dict[str, Any]] = {}

        for item in states:
            state = str(item.get("state") or "unknown")
            if state.lower() not in affected_states:
                continue
            device_id = str(item.get("deviceId") or item.get("id") or "")
            if not device_id:
                continue
            devices[device_id] = {
                "device_id": device_id,
                "device_name": item.get("deviceName") or "Unnamed device",
                "device_model": item.get("deviceModel") or "—",
                "setting_name": item.get("settingName") or item.get("setting") or "Unnamed setting",
                "state": state,
                "grace_period_expires_at": item.get("complianceGracePeriodExpirationDateTime"),
            }

        return sorted(devices.values(), key=lambda item: item["device_name"].lower())
