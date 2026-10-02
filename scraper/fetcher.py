import requests
from urllib.parse import urlparse


def fetch_page(url):
    """
    Fetch HTML content from a URL.
    """

    # Validate URL
    parsed_url = urlparse(url)

    if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
        raise ValueError("Invalid URL. Please provide a valid HTTP or HTTPS URL.")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/154.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )

        response.raise_for_status()

        return response.text

    except requests.exceptions.Timeout:
        raise RuntimeError("The website request timed out.")

    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not connect to the website.")

    except requests.exceptions.HTTPError as error:
        raise RuntimeError(
            f"The website returned an HTTP error: {error}"
        )

    except requests.exceptions.RequestException as error:
        raise RuntimeError(
            f"Failed to fetch the website: {error}"
        )
