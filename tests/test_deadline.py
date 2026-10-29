import time

import pytest
import requests
from unittest.mock import Mock

from scraper.fetcher import _response_text, analysis_deadline, check_analysis_deadline


def test_analysis_deadline_stops_slow_scrape_work():
    with analysis_deadline(0.01):
        time.sleep(0.02)
        with pytest.raises(RuntimeError, match="Analysis timed out"):
            check_analysis_deadline()


def test_streamed_response_cannot_keep_analysis_alive_with_slow_chunks():
    class SlowResponse(requests.Response):
        def iter_content(self, chunk_size):
            time.sleep(0.02)
            yield b"<html>"

    response = SlowResponse()
    response.raw = Mock()
    response.encoding = "utf-8"
    with analysis_deadline(0.01):
        with pytest.raises(RuntimeError, match="Analysis timed out"):
            _response_text(response)
