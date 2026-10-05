from unittest.mock import Mock

import pytest

from app.core.config import Settings
from src.sync.graph_client import DEFAULT_SELECT_FIELDS, GraphClient


def test_graph_reads_injected_settings_and_selects_owner_type():
    config = Settings(_env_file=None, AZURE_TENANT_ID="tenant", AZURE_CLIENT_ID="client", AZURE_CLIENT_SECRET="secret")
    client = GraphClient(config=config)
    assert (client.tenant_id, client.client_id, client.client_secret) == ("tenant", "client", "secret")
    assert "managedDeviceOwnerType" in DEFAULT_SELECT_FIELDS


@pytest.mark.parametrize("limit", [0, -1])
def test_zero_limit_returns_empty_and_negative_is_rejected(limit):
    client = GraphClient(tenant_id="t", client_id="c", client_secret="s")
    client.get_access_token = Mock(return_value="token")
    client._session = Mock()
    if limit == 0:
        assert client.fetch_managed_devices(max_devices=limit) == []
        client.get_access_token.assert_not_called()
        client._session.get.assert_not_called()
    else:
        with pytest.raises(ValueError):
            client.fetch_managed_devices(max_devices=limit)


def test_graph_pagination_follows_next_link():
    client = GraphClient(tenant_id="t", client_id="c", client_secret="s")
    client.get_access_token = Mock(return_value="token")
    first = Mock(status_code=200)
    first.json.return_value = {"value": [{"id": "1"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/next"}
    second = Mock(status_code=200)
    second.json.return_value = {"value": [{"id": "2"}]}
    client._session = Mock()
    client._session.get.side_effect = [first, second]
    assert [row["id"] for row in client.fetch_managed_devices()] == ["1", "2"]


def test_positive_limit_is_applied_to_request_page_size():
    client = GraphClient(tenant_id="t", client_id="c", client_secret="s")
    client.get_access_token = Mock(return_value="token")
    response = Mock(status_code=200)
    response.json.return_value = {"value": [{"id": "1"}, {"id": "2"}]}
    client._session = Mock()
    client._session.get.return_value = response
    assert len(client.fetch_managed_devices(max_devices=2)) == 2
    assert "$top=2" in client._session.get.call_args.args[0]
