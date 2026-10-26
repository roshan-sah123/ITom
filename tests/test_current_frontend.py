"""Only the current built React portal is exposed by the API server."""
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.assets.append(attrs['src'])
        elif tag == 'link' and attrs.get('rel') in {'stylesheet', 'icon'}:
            self.assets.append(attrs['href'])


def test_current_built_portal_and_every_entry_asset_are_served(api_environment):
    with TestClient(api_environment) as client:
        response = client.get('/')
        assert response.status_code == 200
        assert 'Coforge ITOM Operations Portal' in response.text
        parser = AssetParser()
        parser.feed(response.text)
        assert any(asset.startswith('/revamp-assets/') and asset.endswith('.js') for asset in parser.assets)
        for path in parser.assets:
            assert client.get(path).status_code == 200, path


@pytest.mark.parametrize('path', [
    '/legacy.html', '/cmdb_explorer.html', '/infrastructure_analytics.html',
    '/js/app.js', '/js/api.js', '/css/style.css',
    '/not-in-use/legacy-frontend/frontend/index.html',
])
def test_retired_frontend_is_not_publicly_served(api_environment, path):
    with TestClient(api_environment) as client:
        assert client.get(path).status_code == 404
