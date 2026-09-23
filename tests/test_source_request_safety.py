from unittest.mock import Mock

import pytest
import requests

from src.sync.solarwinds_client import SolarWindsClient, SolarWindsApiError, SolarWindsSecurityError


def test_query_parameter_cannot_override_validated_select():
    client = SolarWindsClient(host="test.invalid")
    client._session = Mock()
    with pytest.raises(SolarWindsSecurityError):
        client.query("SELECT NodeID FROM Orion.Nodes", {"query": "DELETE FROM Orion.Nodes"})
    client._session.get.assert_not_called()


def test_tls_failure_never_disables_verification():
    client = SolarWindsClient(host="test.invalid")
    client.verify_ssl = True
    client._session = Mock()
    client._session.get.side_effect = requests.exceptions.SSLError("test certificate failure")
    with pytest.raises(SolarWindsApiError):
        client.query("SELECT NodeID FROM Orion.Nodes")
    assert client._session.get.call_count == 1
    assert client._session.get.call_args.kwargs["verify"] is True


@pytest.mark.parametrize("payload", [{}, {"results": None}, []])
def test_malformed_swis_response_fails(payload):
    client = SolarWindsClient(host="test.invalid")
    client._session = Mock()
    client._session.get.return_value.status_code = 200
    client._session.get.return_value.json.return_value = payload
    with pytest.raises(SolarWindsApiError):
        client.query("SELECT NodeID FROM Orion.Nodes")
