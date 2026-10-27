"""Polite HTTP client: retries with backoff, a per-host rate limit, and an honest User-Agent."""

from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bhavishya._version import __version__

USER_AGENT = f"bhavishya/{__version__} (+https://github.com/Tharun0127/Bhavishya)"


class PoliteClient:
    """A ``requests`` session that waits at least ``min_interval`` seconds between calls to one host.

    Government servers are small. One request per second per host is slow enough not to
    be a burden and fast enough to backfill a year of daily files in a few minutes.
    """

    def __init__(self, min_interval: float = 1.0, timeout: float = 60.0, retries: int = 4) -> None:
        self.min_interval = min_interval
        self.timeout = timeout
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        retry = Retry(
            total=retries,
            backoff_factor=2.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _wait_for_host(self, url: str) -> None:
        host = urlparse(url).netloc
        with self._lock:
            elapsed = time.monotonic() - self._last_call.get(host, 0.0)
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_call[host] = time.monotonic()

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        self._wait_for_host(url)
        return self.session.get(url, timeout=kwargs.pop("timeout", self.timeout), **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        self._wait_for_host(url)
        return self.session.post(url, timeout=kwargs.pop("timeout", self.timeout), **kwargs)
