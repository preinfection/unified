"""Release information from GitHub: "is there a newer Unified?" and the
changelog.

Two endpoints, both public and unauthenticated:

    releases/latest   the newest published release - the update check
    releases          every release - Settings > Changelog

THE RULES THIS MODULE KEEPS, because it runs inside a mail client that
must work with the network off:

  * NEVER ON THE UI THREAD, NEVER DURING STARTUP. Requests run on a
    QThread, and the first check waits until the window has been up for a
    while.
  * AT MOST ONCE AN HOUR, ACROSS RESTARTS. The time of the last attempt is
    persisted - including failed attempts - so restarting the app ten
    times offline does not make ten requests. Conditional requests (ETag)
    mean an unchanged answer costs GitHub's rate limit nothing.
  * SILENT TO THE USER ON FAILURE. Offline, a timeout, a 4xx or 5xx, a rate
    limit, malformed JSON, a release with fields missing, a tag that is not
    a version: every one of these is logged at DEBUG and otherwise means
    "no update shown". A rate-limit answer moves the next attempt to when
    GitHub says the limit resets.
  * VERSIONS COMPARED AS NUMBERS. 1.10.0 is newer than 1.9.0; a string
    comparison says otherwise.
  * ONLY THIS PROJECT'S RELEASE PAGES ARE EVER OPENED. The URL the button
    opens comes from the response, so it is checked to be a github.com
    release page of this repository before it is trusted.

Nothing here downloads or installs anything. The update button opens the
release page in the browser and the user decides.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from app import __version__

log = logging.getLogger(__name__)

REPO = "preinfection/unified"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
LIST_URL = f"https://api.github.com/repos/{REPO}/releases"

CHECK_INTERVAL_S = 60 * 60
# The first check waits this long after the window appears, so it never
# competes with opening the mailbox.
FIRST_CHECK_DELAY_S = 20
TIMEOUT_S = 10
MAX_BODY_BYTES = 2_000_000

# Tests switch this off so the suite never touches the network.
NETWORK_ENABLED = True

_VERSION = re.compile(
    r"^[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


# ------------------------------------------------------------------ versions

def parse_version(tag) -> tuple | None:
    """'v1.10.0' -> (1, 10, 0, ()) ; '1.4.0-beta.2' -> (1, 4, 0, ('beta', 2)).

    None for anything that is not a version, which callers treat as "not
    an update" - never as newer.
    """
    if not isinstance(tag, str):
        return None
    match = _VERSION.match(tag.strip())
    if not match:
        return None
    major, minor, patch, pre = match.groups()
    pre_parts: tuple = ()
    if pre:
        pre_parts = tuple(int(p) if p.isdigit() else p for p in pre.split("."))
    return int(major), int(minor or 0), int(patch or 0), pre_parts


def _pre_key(pre: tuple):
    """SemVer precedence: a release sorts after its own pre-releases, and
    numeric identifiers sort before alphanumeric ones."""
    if not pre:
        return (1,)
    return (0, tuple((0, p, "") if isinstance(p, int) else (1, 0, p) for p in pre))


def version_key(version: tuple):
    major, minor, patch, pre = version
    return (major, minor, patch, _pre_key(pre))


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    if a is None or b is None:
        return False
    return version_key(a) > version_key(b)


def display_version(tag: str) -> str:
    parsed = parse_version(tag)
    if parsed is None:
        return tag
    text = f"{parsed[0]}.{parsed[1]}.{parsed[2]}"
    if parsed[3]:
        text += "-" + ".".join(str(p) for p in parsed[3])
    return text


# ------------------------------------------------------------------ releases

@dataclass(frozen=True)
class Release:
    tag: str
    version: str
    url: str
    name: str
    published_at: str
    body: str

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data) -> "Release | None":
        if not isinstance(data, dict):
            return None
        try:
            return cls(**{k: str(data[k]) for k in
                          ("tag", "version", "url", "name", "published_at", "body")})
        except (KeyError, TypeError):
            return None


def is_release_page(url) -> bool:
    """Only a github.com release page of THIS repository may be opened."""
    if not isinstance(url, str):
        return False
    parts = urlparse(url)
    return (
        parts.scheme == "https"
        and parts.netloc.lower() == "github.com"
        and parts.path.lower().startswith(f"/{REPO}/releases/")
    )


def parse_release(item) -> Release | None:
    """One release object from the API, or None if it is not something the
    app should offer: a draft, a pre-release, a missing or unparsable tag,
    or a page that is not this repository's."""
    if not isinstance(item, dict):
        return None
    if item.get("draft") or item.get("prerelease"):
        return None
    tag = item.get("tag_name")
    if parse_version(tag) is None:
        return None
    url = item.get("html_url")
    if not is_release_page(url):
        return None
    name = item.get("name")
    body = item.get("body")
    published = item.get("published_at") or item.get("created_at") or ""
    return Release(
        tag=tag,
        version=display_version(tag),
        url=url,
        name=name if isinstance(name, str) else "",
        published_at=published if isinstance(published, str) else "",
        body=body if isinstance(body, str) else "",
    )


def parse_release_list(payload) -> list[Release]:
    """Every offerable release, newest first by version (then date)."""
    if not isinstance(payload, list):
        raise ValueError("release list is not a list")
    releases = [r for r in (parse_release(item) for item in payload) if r]
    releases.sort(
        key=lambda r: (version_key(parse_version(r.tag)), r.published_at),
        reverse=True,
    )
    return releases


# ------------------------------------------------------------------ transport

class FetchError(Exception):
    def __init__(self, reason: str, retry_at: float | None = None):
        super().__init__(reason)
        self.retry_at = retry_at


def fetch_json(url: str, etag: str = "", *, timeout: float = TIMEOUT_S):
    """GET `url`. Returns (status, payload, etag); status 304 means the
    cached copy is still current and payload is None.

    Raises FetchError for everything else, with retry_at set when GitHub
    said when to come back (rate limiting).
    """
    if not NETWORK_ENABLED:
        raise FetchError("network disabled")
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"Unified/{__version__}",
        **({"If-None-Match": etag} if etag else {}),
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
            if len(raw) > MAX_BODY_BYTES:
                raise FetchError("response too large")
            payload = json.loads(raw.decode("utf-8"))
            return response.status, payload, response.headers.get("ETag", "") or ""
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return 304, None, etag
        retry_at = None
        if e.code in (403, 429):
            retry_at = _retry_time(e.headers)
        raise FetchError(f"HTTP {e.code}", retry_at) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FetchError(f"unreachable ({getattr(e, 'reason', e)})") from None
    except (ValueError, UnicodeDecodeError) as e:
        raise FetchError(f"malformed response ({e})") from None


def _retry_time(headers) -> float | None:
    if headers is None:
        return None
    after = headers.get("Retry-After")
    if after and str(after).isdigit():
        return time.time() + int(after)
    reset = headers.get("X-RateLimit-Reset")
    if reset and str(reset).isdigit():
        return float(reset)
    return None


class _FetchWorker(QThread):
    done = Signal(int, object, str)   # status, payload, etag
    failed = Signal(str, object)      # reason, retry_at

    def __init__(self, url: str, etag: str, fetch, parent=None):
        super().__init__(parent)
        self._url, self._etag, self._fetch = url, etag, fetch

    def run(self) -> None:
        try:
            status, payload, etag = self._fetch(self._url, self._etag)
        except FetchError as e:
            self.failed.emit(str(e), e.retry_at)
        except Exception as e:  # a bug here must never reach the user
            self.failed.emit(f"unexpected {type(e).__name__}: {e}", None)
        else:
            self.done.emit(int(status), payload, etag or "")


# ------------------------------------------------------------- update check

class UpdateChecker(QObject):
    """Asks releases/latest at most once an hour and says whether the
    newest published release is newer than this build.

    update_changed(Release | None) - None means "no update to offer".

    State lives in Settings under "update_check": the time of the last
    attempt, the ETag, the release last seen, and any retry-after time.
    """

    update_changed = Signal(object)

    def __init__(self, settings, current_version: str = __version__,
                 parent=None, *, fetch=fetch_json, clock=time.time):
        super().__init__(parent)
        self._settings = settings
        self._current = current_version
        self._fetch = fetch
        self._clock = clock
        self._worker: _FetchWorker | None = None
        self._available: Release | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.check_now)

    # -------------------------------------------------------------- state

    def _state(self) -> dict:
        state = self._settings.get("update_check")
        return dict(state) if isinstance(state, dict) else {}

    def _save(self, **changes) -> None:
        state = self._state()
        state.update(changes)
        self._settings.set("update_check", state)

    def available(self) -> Release | None:
        return self._available

    def _offer(self, release: Release | None) -> None:
        if release is not None and not is_newer(release.tag, self._current):
            release = None
        if release == self._available:
            return
        self._available = release
        self.update_changed.emit(release)

    # ----------------------------------------------------------- schedule

    def start(self) -> None:
        """Offer what the last check found, then schedule the next one.

        A remembered newer release is offered straight away, from disk -
        the button does not have to wait for the network to reappear.
        """
        self._offer(Release.from_json(self._state().get("latest")))
        self._schedule(first=True)

    def seconds_until_due(self) -> float:
        state = self._state()
        now = self._clock()
        due = float(state.get("checked_at", 0) or 0) + CHECK_INTERVAL_S
        retry = float(state.get("retry_at", 0) or 0)
        return max(0.0, max(due, retry) - now)

    def _schedule(self, *, first: bool = False) -> None:
        wait = self.seconds_until_due()
        if first:
            wait = max(wait, FIRST_CHECK_DELAY_S)
        # QTimer takes an int of milliseconds; clamp to a day so a far
        # retry-after cannot overflow it.
        self._timer.start(int(min(wait, 86_400) * 1000))

    def next_check_in(self) -> float:
        return self._timer.remainingTime() / 1000.0 if self._timer.isActive() else -1.0

    def check_now(self) -> bool:
        """Start a check if one is due and none is running. Returns whether
        it started."""
        if self._worker is not None:
            return False
        if self.seconds_until_due() > 0:
            self._schedule()
            return False
        # The attempt is recorded BEFORE it is made, so a crash or an
        # offline machine still counts as having asked this hour.
        self._save(checked_at=self._clock())
        worker = _FetchWorker(LATEST_URL, str(self._state().get("etag") or ""),
                              self._fetch, self)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        self._worker = worker
        worker.start()
        return True

    def _on_done(self, status: int, payload, etag: str) -> None:
        if status == 304:
            log.debug("Update check: unchanged since the last check")
            self._offer(Release.from_json(self._state().get("latest")))
            return
        release = parse_release(payload)
        if release is None:
            log.debug("Update check: the latest release is not usable")
            return
        self._save(etag=etag, latest=release.to_json(), retry_at=0)
        if is_newer(release.tag, self._current):
            log.info("Unified %s is available", release.version)
        self._offer(release)

    def _on_failed(self, reason: str, retry_at) -> None:
        log.debug("Update check failed: %s", reason)
        if retry_at:
            self._save(retry_at=float(retry_at))

    def _on_finished(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()
        self._schedule()

    def shutdown(self) -> None:
        self._timer.stop()
        if self._worker is not None:
            self._worker.wait(int(TIMEOUT_S * 1000) + 500)


# ---------------------------------------------------------------- changelog

class ReleaseNotesStore(QObject):
    """The release list for Settings > Changelog, cached on disk.

    Reads the cache first so the page is never empty when a copy exists,
    and asks the network only when the copy is older than an hour. A
    failure keeps whatever was cached and says so.

    changed(list[Release], status) with status one of:
        "fresh"     just fetched (or confirmed unchanged)
        "cached"    from disk, still within the hour
        "stale"     from disk; a refresh failed
        "loading"   nothing on disk yet, a request is running
        "failed"    nothing on disk and the request failed
        "empty"     the request succeeded and there are no releases
    """

    changed = Signal(list, str)

    def __init__(self, path: Path, parent=None, *, fetch=fetch_json,
                 clock=time.time):
        super().__init__(parent)
        self._path = Path(path)
        self._fetch = fetch
        self._clock = clock
        self._worker: _FetchWorker | None = None
        self.releases: list[Release] = []
        self.status = "loading"
        self.fetched_at = 0.0
        self._etag = ""
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        releases = [r for r in (Release.from_json(x) for x in data.get("releases", []))
                    if r is not None]
        self.releases = releases
        self.fetched_at = float(data.get("fetched_at", 0) or 0)
        self._etag = str(data.get("etag") or "")

    def _store(self) -> None:
        try:
            self._path.write_text(json.dumps({
                "fetched_at": self.fetched_at,
                "etag": self._etag,
                "releases": [r.to_json() for r in self.releases],
            }), encoding="utf-8")
        except OSError as e:
            log.debug("Could not cache release notes: %s", e)

    def is_stale(self) -> bool:
        return self._clock() - self.fetched_at >= CHECK_INTERVAL_S

    def refresh(self) -> None:
        """Show what is cached now; fetch if the cache is an hour old."""
        if self.releases:
            self._emit("cached")
            if not self.is_stale():
                return
        if self._worker is not None:
            return
        if not self.releases:
            self._emit("loading")
        worker = _FetchWorker(LIST_URL, self._etag if self.releases else "",
                              self._fetch, self)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        self._worker = worker
        worker.start()

    def _emit(self, status: str) -> None:
        self.status = status
        self.changed.emit(list(self.releases), status)

    def _on_done(self, status: int, payload, etag: str) -> None:
        self.fetched_at = self._clock()
        if status == 304:
            self._store()
            self._emit("fresh")
            return
        try:
            self.releases = parse_release_list(payload)
        except ValueError as e:
            log.debug("Release list unusable: %s", e)
            self._emit("stale" if self.releases else "failed")
            return
        self._etag = etag
        self._store()
        self._emit("fresh" if self.releases else "empty")

    def _on_failed(self, reason: str, retry_at) -> None:
        log.debug("Release notes fetch failed: %s", reason)
        self._emit("stale" if self.releases else "failed")

    def _on_finished(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.wait(int(TIMEOUT_S * 1000) + 500)
