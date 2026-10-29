from unittest.mock import Mock

import pytest

from scraper import fetcher


def test_rejects_local_and_credentialed_urls():
    with pytest.raises(ValueError, match="private"):
        fetcher.validate_public_url("http://127.0.0.1:5000/")
    with pytest.raises(ValueError, match="credentials"):
        fetcher.validate_public_url("https://user:secret@example.com/")


def test_robots_disallow_stops_before_page_fetch(monkeypatch):
    fetcher._robots_cache.clear()
    robots = Mock(status_code=200, headers={}, text="User-agent: *\nDisallow: /private", is_redirect=False)
    requests = []
    monkeypatch.setattr(fetcher, "_polite_get", lambda url: requests.append(url) or robots)
    monkeypatch.setattr(fetcher, "validate_public_url", lambda url: url)
    with pytest.raises(RuntimeError, match="robots.txt"):
        fetcher.fetch_page("https://example.com/private")
    assert requests == ["https://example.com/robots.txt"]


def test_robots_not_found_allows_public_page(monkeypatch):
    fetcher._robots_cache.clear()
    robots = Mock(status_code=404, headers={}, text="", is_redirect=False)
    page = Mock(status_code=200, headers={"Content-Type": "text/html"}, text="<h1>Product</h1>", is_redirect=False)
    responses = iter([robots, page])
    monkeypatch.setattr(fetcher, "_polite_get", lambda _url: next(responses))
    monkeypatch.setattr(fetcher, "validate_public_url", lambda url: url)
    assert fetcher.fetch_page("https://example.com/product") == "<h1>Product</h1>"


def test_browser_resource_respects_robots_before_fetch(monkeypatch):
    rules = Mock()
    rules.can_fetch.return_value = False
    monkeypatch.setattr(fetcher, "validate_public_url", lambda url: url)
    monkeypatch.setattr(fetcher, "_fetch_robots", lambda _origin: rules)
    monkeypatch.setattr(fetcher, "_polite_get", lambda *_args, **_kwargs: pytest.fail("disallowed resource was requested"))
    with pytest.raises(RuntimeError, match="robots.txt"):
        fetcher.fetch_render_resource("https://example.com/private.js")
