"""Careful, robots-aware HTTP fetching for public product pages."""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from functools import wraps
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

USER_AGENT = "PriceAnalyzerBot/1.0"
REQUEST_DELAY_SECONDS = 1.0
MAX_REDIRECTS = 5
_lock = threading.Lock()
_thread_local = threading.local()
_last_request: dict[str, float] = {}
_robots_cache: dict[str, tuple[float, RobotFileParser | None]] = {}
_ROBOTS_TTL = 3600
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_deadline = ContextVar("pricelens_analysis_deadline", default=None)


class AnalysisTimeout(RuntimeError):
    """The overall polite analysis budget expired."""


@contextmanager
def analysis_deadline(seconds: float = 90):
    """Bound all polite fetch and pacing work in one analysis request."""
    token = _deadline.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


def bounded_analysis(function):
    """Give direct scraper/fetcher entry points the same finite wall-clock budget."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _deadline.get() is not None:
            return function(*args, **kwargs)
        with analysis_deadline():
            return function(*args, **kwargs)
    return wrapped


def _remaining_seconds() -> float | None:
    deadline = _deadline.get()
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AnalysisTimeout("Analysis timed out while contacting the website. Try one page or a different public URL.")
    return remaining


def check_analysis_deadline() -> None:
    """Fail promptly between pages and optional enrichment requests."""
    _remaining_seconds()


def validate_public_url(url: str) -> str:
    """Normalize an HTTP(S) URL and reject local/private network targets."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Please provide a valid public HTTP or HTTPS URL.")
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Please provide a valid public HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing embedded credentials are not supported.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The URL contains an invalid port.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("The URL contains an invalid port.")
    host = parsed.hostname.rstrip(".").encode("idna").decode("ascii")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(result[4][0])
                for result in socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            }
        except OSError as exc:
            raise RuntimeError("The website host could not be resolved.") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Local and private network URLs are not supported.")
    netloc = host
    if ":" in host:
        netloc = f"[{host}]"
    if port:
        netloc = f"{netloc}:{port}"
    return parsed._replace(netloc=netloc, fragment="").geturl()


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _get_session() -> requests.Session:
    """Reuse HTTP connections within each worker thread."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        _thread_local.session = session
    return session


def _polite_get(url: str, accept: str = "text/html,application/xhtml+xml") -> requests.Response:
    remaining = _remaining_seconds()
    host = urlparse(url).netloc.lower()
    with _lock:
        elapsed = time.monotonic() - _last_request.get(host, 0.0)
        if elapsed < REQUEST_DELAY_SECONDS:
            delay = REQUEST_DELAY_SECONDS - elapsed
            if remaining is not None:
                delay = min(delay, remaining)
            time.sleep(delay)
        remaining = _remaining_seconds()
        connect_timeout = 3 if remaining is None else max(0.2, min(3, remaining))
        read_timeout = 8 if remaining is None else max(0.2, min(8, remaining))
        _last_request[host] = time.monotonic()
    return _get_session().get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
        timeout=(connect_timeout, read_timeout),
        allow_redirects=False,
        stream=True,
    )


def _response_text(response: requests.Response) -> str:
    """Read a streamed body under the absolute analysis deadline and size cap."""
    if not isinstance(response, requests.Response):
        return response.text
    chunks = []
    size = 0
    try:
        for chunk in response.iter_content(chunk_size=16_384):
            check_analysis_deadline()
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise RuntimeError("The website response is too large to analyze safely.")
            chunks.append(chunk)
    except requests.Timeout as exc:
        raise RuntimeError("The website request timed out.") from exc
    except requests.ConnectionError as exc:
        raise RuntimeError("The connection closed while reading the website response.") from exc
    except requests.RequestException as exc:
        raise RuntimeError("The website response could not be read completely.") from exc
    finally:
        response.close()
    encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace")


def _fetch_robots(origin: str) -> RobotFileParser | None:
    cached = _robots_cache.get(origin)
    now = time.monotonic()
    if cached and now - cached[0] < _ROBOTS_TTL:
        return cached[1]

    robots_url = f"{origin}/robots.txt"
    for _ in range(MAX_REDIRECTS + 1):
        robots_url = validate_public_url(robots_url)
        try:
            response = _polite_get(robots_url)
        except requests.RequestException as exc:
            raise RuntimeError("Could not verify this site's robots.txt; scraping was stopped.") from exc
        if response.is_redirect:
            response.close()
            location = response.headers.get("Location")
            if not location:
                raise RuntimeError("The site's robots.txt redirect is invalid; scraping was stopped.")
            robots_url = urljoin(robots_url, location)
            continue
        if response.status_code == 404:
            response.close()
            _robots_cache[origin] = (now, None)
            return None
        if response.status_code in (401, 403):
            response.close()
            raise RuntimeError("This site restricts access to robots.txt; scraping was stopped.")
        if not 200 <= response.status_code < 300:
            response.close()
            raise RuntimeError(f"Could not verify this site's robots.txt (HTTP {response.status_code}); scraping was stopped.")
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(_response_text(response).splitlines())
        _robots_cache[origin] = (now, parser)
        return parser
    raise RuntimeError("Too many redirects while checking robots.txt.")


@bounded_analysis
def fetch_page(url: str) -> str:
    """Fetch a public HTML page only when the site permits our user agent."""
    current_url = validate_public_url(url)
    for redirect_count in range(MAX_REDIRECTS + 1):
        _remaining_seconds()
        origin = _origin(current_url)
        rules = _fetch_robots(origin)
        if rules and not rules.can_fetch(USER_AGENT, current_url):
            raise RuntimeError("This page is disallowed by the site's robots.txt.")
        try:
            response = _polite_get(current_url)
        except requests.Timeout as exc:
            raise RuntimeError("The website request timed out.") from exc
        except requests.ConnectionError as exc:
            raise RuntimeError("Could not connect to the website.") from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to fetch the website: {exc}") from exc
        if response.is_redirect:
            response.close()
            if redirect_count == MAX_REDIRECTS:
                raise RuntimeError("Too many redirects while fetching the website.")
            location = response.headers.get("Location")
            if not location:
                raise RuntimeError("The website returned an invalid redirect.")
            current_url = validate_public_url(urljoin(current_url, location))
            continue
        if response.status_code in (401, 403, 429):
            response.close()
            raise RuntimeError(f"The website denied or rate-limited access (HTTP {response.status_code}); scraping was stopped.")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            response.close()
            raise RuntimeError(f"The website returned an HTTP error: {exc}") from exc
        content_type = response.headers.get("Content-Type", "")
        if content_type and not any(kind in content_type.lower() for kind in ("text/html", "application/xhtml+xml")):
            response.close()
            raise RuntimeError("The URL did not return an HTML page.")
        body = _response_text(response)
        _remaining_seconds()
        lowered = body[:20000].lower()
        if any(marker in lowered for marker in ("captcha", "verify you are human", "unusual traffic", "access denied")):
            raise RuntimeError("The site presented an access challenge. Sign-in and CAPTCHA challenges are not supported.")
        return body
    raise RuntimeError("Unable to fetch the website.")


def fetch_render_resource(url: str):
    """Fetch one browser resource only after public-URL, robots, and pacing checks."""
    current_url = validate_public_url(url)
    for redirect_count in range(MAX_REDIRECTS + 1):
        _remaining_seconds()
        origin = _origin(current_url)
        rules = _fetch_robots(origin)
        if rules and not rules.can_fetch(USER_AGENT, current_url):
            raise RuntimeError("A page resource is disallowed by the site's robots.txt.")
        try:
            response = _polite_get(current_url, accept="*/*")
        except requests.Timeout as exc:
            raise RuntimeError("A page resource request timed out.") from exc
        if response.is_redirect:
            response.close()
            location = response.headers.get("Location")
            if not location or redirect_count == MAX_REDIRECTS:
                raise RuntimeError("A page resource returned an invalid or excessive redirect.")
            current_url = validate_public_url(urljoin(current_url, location))
            continue
        if response.status_code in (401, 403, 429):
            response.close()
            raise RuntimeError(f"The website denied or rate-limited a browser resource (HTTP {response.status_code}).")
        status = response.status_code
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        chunks = []
        size = 0
        try:
            for chunk in response.iter_content(chunk_size=16_384):
                check_analysis_deadline()
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise RuntimeError("A page resource is too large to load safely.")
                chunks.append(chunk)
        except requests.RequestException as exc:
            raise RuntimeError("A page resource could not be read completely.") from exc
        finally:
            response.close()
        body = b"".join(chunks)
        if "html" in content_type.lower():
            lowered = body[:20000].decode("utf-8", errors="ignore").lower()
            if any(marker in lowered for marker in ("captcha", "verify you are human", "unusual traffic", "access denied")):
                raise RuntimeError("The site presented an access challenge; JavaScript rendering stopped.")
        safe_headers = {"Content-Type": content_type}
        for name in ("Cache-Control", "Access-Control-Allow-Origin", "Access-Control-Allow-Credentials", "Access-Control-Allow-Headers", "Access-Control-Allow-Methods"):
            if response.headers.get(name):
                safe_headers[name] = response.headers[name]
        return status, safe_headers, body
    raise RuntimeError("Too many redirects while loading page resources.")
