"""
Unit tests for the discovery crawler.
"""
from unittest.mock import MagicMock


def test_get_site_name_for_url_matches_configured_site_host():
    from src.config.site_configs import get_site_name_for_url

    assert get_site_name_for_url("https://www.ubos.org/publication/report.pdf") == "ubos"
    assert get_site_name_for_url("https://ubos.org/publication/report.pdf") == "ubos"
    assert get_site_name_for_url("https://unknown.example/report.pdf") is None


def test_crawl_site_verifies_ssl_by_default(monkeypatch):
    from src.flows import discovery

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "<html><body></body></html>"
    mock_response.raise_for_status.return_value = None
    mock_client.get.return_value = mock_response

    mock_client_cls = MagicMock(return_value=mock_client)
    monkeypatch.setattr(discovery.httpx, "Client", mock_client_cls)
    monkeypatch.setattr(discovery.time, "sleep", lambda _: None)

    discovery.crawl_site.fn("ubos")

    assert mock_client_cls.call_args.kwargs["verify"] is True


def test_crawl_site_can_disable_ssl_verification(monkeypatch):
    from src.flows import discovery

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "<html><body></body></html>"
    mock_response.raise_for_status.return_value = None
    mock_client.get.return_value = mock_response

    mock_client_cls = MagicMock(return_value=mock_client)
    monkeypatch.setattr(discovery.httpx, "Client", mock_client_cls)
    monkeypatch.setattr(discovery.time, "sleep", lambda _: None)
    monkeypatch.setattr(discovery.settings, "crawl_unverify_ssl", "ubos")

    discovery.crawl_site.fn("ubos")

    assert mock_client_cls.call_args.kwargs["verify"] is False


def test_crawl_site_keeps_verification_for_other_sites(monkeypatch):
    from src.flows import discovery

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "<html><body></body></html>"
    mock_response.raise_for_status.return_value = None
    mock_client.get.return_value = mock_response

    mock_client_cls = MagicMock(return_value=mock_client)
    monkeypatch.setattr(discovery.httpx, "Client", mock_client_cls)
    monkeypatch.setattr(discovery.time, "sleep", lambda _: None)
    monkeypatch.setattr(discovery.settings, "crawl_unverify_ssl", "ubos")

    discovery.crawl_site.fn("naro")

    assert mock_client_cls.call_args.kwargs["verify"] is True
