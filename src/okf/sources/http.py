"""GET JSON for connectors: timeouts, retries on 429, errors as "unknown", and a fixtures mode.

`OKF_SOURCES_FIXTURES=<dir>` answers from files instead of the network (demos, tests): a request
for `/wiki/api/v2/pages/131073?body-format=storage` reads `<dir>/wiki/api/v2/pages/131073.json`, or
`131073@version=12.json` when the request carries `version=12` (the file with the most matching
query parameters wins). A fixture `{"_status": 404}` answers with that HTTP status.

Credentials go only in headers built by the connector for its configured host and are never
part of a message: errors name the HTTP status and the path, nothing else.
"""

from __future__ import annotations

import base64
import email.utils
import json
import math
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import parse_qsl, urlsplit

from okf import __version__
from okf.sources.base import Unavailable

RETRY_STATUSES = {429, 502, 503, 504}
MAX_PAUSE = 30.0
AUTH_HELP = "check OKF_ATLASSIAN_EMAIL and OKF_ATLASSIAN_TOKEN (Cloud) or OKF_ATLASSIAN_PAT (Server/DC)"


class Http:
    def __init__(self, env: Mapping[str, str] | None = None, sleep: Callable[[float], None] = time.sleep,
                 retries: int = 3):
        env = env or {}
        self.fixtures = Path(env["OKF_SOURCES_FIXTURES"]) if env.get("OKF_SOURCES_FIXTURES") else None
        self.timeout = float(env.get("OKF_SOURCES_TIMEOUT") or 10)
        self.sleep = sleep
        self.retries = retries
        self.requests = 0  # for tests: no settings, no requests
        self._down: dict[str, str] = {}  # host -> why it could not be reached: fail fast after the first time

    def get_json(self, url: str, headers: Mapping[str, str] | None = None):
        self.requests += 1
        parts = urlsplit(url)
        where = parts.path or "/"
        if self.fixtures is not None:
            return self._fixture(parts)
        if parts.netloc in self._down:
            raise Unavailable(self._down[parts.netloc])
        request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": f"okf-ai/{__version__}", **(headers or {})})
        try:
            body = fetch(request, self.timeout, self.retries, self.sleep)
        except HttpFailure as failure:
            if failure.status is not None:
                raise Unavailable(status_message(failure.status, where, failure.tries)) from None
            self._down[parts.netloc] = f"{parts.hostname} {'timed out' if failure.timed_out else 'cannot connect'}"
            raise Unavailable(self._down[parts.netloc]) from None
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Unavailable(f"GET {where}: the answer is not JSON") from None

    def _fixture(self, parts):
        relative = parts.path.strip("/")
        folder = self.fixtures / Path(relative).parent
        stem = Path(relative).name
        query = dict(parse_qsl(parts.query))
        best, best_size = None, -1
        for path in sorted(folder.glob(f"{stem}*.json")) if folder.is_dir() else []:
            name = path.name[: -len(".json")]
            if name == stem:
                params = {}
            elif name.startswith(stem + "@"):
                params = dict(parse_qsl(name[len(stem) + 1 :]))
            else:
                continue
            if all(query.get(k) == v for k, v in params.items()) and len(params) > best_size:
                best, best_size = path, len(params)
        if best is None:
            raise Unavailable(f"no fixture for GET /{relative} in {self.fixtures}")
        data = json.loads(best.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("_status"), int):
            raise Unavailable(status_message(data["_status"], "/" + relative, 1))
        return data


def status_message(status: int, where: str, tries: int) -> str:
    if status == 401:
        return f"authentication failed (HTTP 401): {AUTH_HELP}"
    if status == 403:
        return "no access (HTTP 403)"
    if status == 404:
        return "not found or no access (HTTP 404)"
    if status == 429:
        return f"rate limited (HTTP 429), gave up after {tries} tries"
    return f"GET {where}: HTTP {status}"


def atlassian_headers(env: Mapping[str, str]) -> dict[str, str]:
    """Bearer for a Server/DC personal access token, Basic email:token for Cloud, nothing otherwise."""
    if env.get("OKF_ATLASSIAN_PAT"):
        return {"Authorization": f"Bearer {env['OKF_ATLASSIAN_PAT']}"}
    if env.get("OKF_ATLASSIAN_EMAIL") and env.get("OKF_ATLASSIAN_TOKEN"):
        pair = f"{env['OKF_ATLASSIAN_EMAIL']}:{env['OKF_ATLASSIAN_TOKEN']}".encode("utf-8")
        return {"Authorization": "Basic " + base64.b64encode(pair).decode("ascii")}
    return {}


class HttpFailure(Exception):
    """A request that did not succeed: an HTTP status (after the retries), or no answer at all."""

    def __init__(self, status: int | None, tries: int, reason: BaseException | None = None):
        super().__init__(status)
        self.status, self.tries, self.reason = status, tries, reason

    @property
    def timed_out(self) -> bool:
        return isinstance(self.reason, (socket.timeout, TimeoutError))


def fetch(request: urllib.request.Request, timeout: float, retries: int = 3,
          sleep: Callable[[float], None] = time.sleep) -> bytes:
    """The body of a successful answer. 429 and 502-504 are retried `retries` times, waiting as
    Retry-After asks (at most 30 s) or 1, 2, 4 s; every other failure raises HttpFailure at once.
    Connectors and okf notify both send through here."""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_STATUSES and attempt < retries:
                sleep(retry_pause(exc.headers.get("Retry-After"), attempt))
                continue
            raise HttpFailure(exc.code, attempt + 1) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            raise HttpFailure(None, attempt + 1, getattr(exc, "reason", exc)) from None
    raise HttpFailure(None, retries + 1)  # not reached: the last attempt returns or raises


def retry_pause(retry_after: str | None, attempt: int) -> float:
    """Seconds to wait: Retry-After (seconds or an HTTP date) clamped to 0..30, else 2**attempt."""
    seconds = None
    if retry_after:
        try:
            seconds = float(retry_after)
        except ValueError:
            try:
                when = email.utils.parsedate_to_datetime(retry_after)
                seconds = (when - datetime.now(when.tzinfo or timezone.utc)).total_seconds()
            except (TypeError, ValueError, IndexError):
                seconds = None
    if seconds is None or not math.isfinite(seconds):
        return float(2 ** attempt)
    return min(max(seconds, 0.0), MAX_PAUSE)
