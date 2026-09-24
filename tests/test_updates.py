"""Update checking and the changelog: versions, failure handling, caching,
and the two surfaces that show the result.

No test here touches the network - conftest.py switches it off for the
whole suite, and every request below goes through an injected fake.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
import urllib.error

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from app import config
from app.services import updates as u
from app.services.updates import (
    FetchError,
    Release,
    ReleaseNotesStore,
    UpdateChecker,
    is_newer,
    parse_release,
    parse_release_list,
    parse_version,
)
from app.ui import motion, theme as t


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def wait_for(predicate, timeout_ms: int = 3000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return True
        loop = QEventLoop()
        QTimer.singleShot(15, loop.quit)
        loop.exec()
    return predicate()


def release_json(tag="v1.5.0", **over) -> dict:
    data = {
        "tag_name": tag,
        "name": f"Unified {tag}",
        "html_url": f"https://github.com/preinfection/unified/releases/tag/{tag}",
        "published_at": "2026-10-01T10:00:00Z",
        "body": "## What changed\n\n- One thing\n- Another",
        "draft": False,
        "prerelease": False,
    }
    data.update(over)
    return data


# ================================================================ versions

@pytest.mark.parametrize("tag, expected", [
    ("v1.10.0", (1, 10, 0, ())),
    ("1.4.0", (1, 4, 0, ())),
    ("V2", (2, 0, 0, ())),
    ("1.4", (1, 4, 0, ())),
    ("1.5.0-beta.2", (1, 5, 0, ("beta", 2))),
    ("1.5.0+build.7", (1, 5, 0, ())),
])
def test_versions_parse(tag, expected):
    assert parse_version(tag) == expected


@pytest.mark.parametrize("tag", ["", "garbage", "v1.x", "1..2", "release-1.2", None, 12])
def test_non_versions_are_refused(tag):
    assert parse_version(tag) is None


@pytest.mark.parametrize("candidate, current, newer", [
    ("1.10.0", "1.9.0", True),        # a string comparison says False
    ("1.4.1", "1.4.0", True),
    ("v1.4.0", "1.4.0", False),
    ("1.3.0", "1.4.0", False),
    ("v2.0", "1.99.99", True),
    ("1.5.0-beta.1", "1.4.0", True),
    ("1.4.0-rc.1", "1.4.0", False),   # a release outranks its own candidates
    ("1.4.0", "1.4.0-rc.1", True),
    ("1.4.0-rc.10", "1.4.0-rc.9", True),
    ("garbage", "1.0.0", False),      # unparsable is never "newer"
])
def test_versions_compare_as_numbers(candidate, current, newer):
    assert is_newer(candidate, current) is newer


# ================================================================ releases

def test_a_good_release_parses():
    release = parse_release(release_json("v1.5.0"))
    assert release.version == "1.5.0"
    assert release.url.endswith("/releases/tag/v1.5.0")


@pytest.mark.parametrize("payload", [
    None, [], "string", {},
    release_json(draft=True),
    release_json(prerelease=True),
    release_json(tag_name=None),
    release_json(tag_name="nightly"),
    release_json(html_url=None),
    release_json(html_url="https://evil.example/releases/tag/v9"),
    release_json(html_url="http://github.com/preinfection/unified/releases/tag/v9"),
    release_json(html_url="https://github.com/someone/else/releases/tag/v9"),
])
def test_unusable_releases_are_not_offered(payload):
    assert parse_release(payload) is None


def test_missing_optional_fields_do_not_break_a_release():
    data = release_json()
    del data["body"], data["name"], data["published_at"]
    release = parse_release(data)
    assert release is not None and release.body == "" and release.name == ""


def test_the_list_is_newest_first_by_version():
    payload = [release_json("1.2.0"), release_json("v1.10.0"),
               release_json("1.9.0"), release_json("v1.3.0", draft=True)]
    assert [r.version for r in parse_release_list(payload)] == ["1.10.0", "1.9.0", "1.2.0"]


def test_a_list_that_is_not_a_list_is_an_error():
    with pytest.raises(ValueError):
        parse_release_list({"message": "Not Found"})


# =============================================================== transport

class _Response(io.BytesIO):
    def __init__(self, body: bytes, status=200, etag='"abc"'):
        super().__init__(body)
        self.status = status
        self.headers = {"ETag": etag}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def network(monkeypatch):
    monkeypatch.setattr(u, "NETWORK_ENABLED", True)
    return monkeypatch


def test_fetch_returns_payload_and_etag(network):
    network.setattr(u.urllib.request, "urlopen",
                    lambda req, timeout: _Response(json.dumps({"a": 1}).encode()))
    assert u.fetch_json(u.LATEST_URL) == (200, {"a": 1}, '"abc"')


def test_fetch_sends_the_etag_and_understands_304(network):
    seen = {}

    def urlopen(req, timeout):
        seen["etag"] = req.get_header("If-none-match")
        seen["timeout"] = timeout
        raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)

    network.setattr(u.urllib.request, "urlopen", urlopen)
    assert u.fetch_json(u.LATEST_URL, '"abc"') == (304, None, '"abc"')
    assert seen == {"etag": '"abc"', "timeout": u.TIMEOUT_S}


@pytest.mark.parametrize("error", [
    urllib.error.URLError("offline"),
    TimeoutError("timed out"),
    ConnectionResetError("reset"),
    urllib.error.HTTPError("u", 500, "Server Error", {}, None),
    urllib.error.HTTPError("u", 404, "Not Found", {}, None),
])
def test_every_network_failure_is_one_quiet_error(network, error):
    def urlopen(req, timeout):
        raise error

    network.setattr(u.urllib.request, "urlopen", urlopen)
    with pytest.raises(FetchError):
        u.fetch_json(u.LATEST_URL)


def test_rate_limiting_says_when_to_come_back(network):
    reset = int(time.time()) + 1800

    def urlopen(req, timeout):
        raise urllib.error.HTTPError(
            "u", 403, "rate limited", {"X-RateLimit-Reset": str(reset)}, None
        )

    network.setattr(u.urllib.request, "urlopen", urlopen)
    with pytest.raises(FetchError) as info:
        u.fetch_json(u.LATEST_URL)
    assert info.value.retry_at == reset


@pytest.mark.parametrize("body", [b"<html>not json</html>", b"\xff\xfe\x00", b""])
def test_malformed_responses_are_errors_not_crashes(network, body):
    network.setattr(u.urllib.request, "urlopen", lambda req, timeout: _Response(body))
    with pytest.raises(FetchError):
        u.fetch_json(u.LATEST_URL)


def test_an_oversized_response_is_refused(network):
    network.setattr(u.urllib.request, "urlopen",
                    lambda req, timeout: _Response(b"[" + b" " * (u.MAX_BODY_BYTES + 2)))
    with pytest.raises(FetchError):
        u.fetch_json(u.LATEST_URL)


def test_the_suite_cannot_reach_the_network():
    with pytest.raises(FetchError):
        u.fetch_json(u.LATEST_URL)


# ============================================================ update checker

class FakeFetch:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []
        self.threads = []

    def __call__(self, url, etag=""):
        self.calls.append((url, etag))
        self.threads.append(threading.current_thread())
        result = self.results.pop(0) if self.results else FetchError("offline")
        if isinstance(result, Exception):
            raise result
        return result


class Clock:
    def __init__(self, now=1_900_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture()
def settings(tmp_path):
    return config.Settings(tmp_path / "settings.json")


def make_checker(settings, fetch, clock, current="1.4.0"):
    checker = UpdateChecker(settings, current, fetch=fetch, clock=clock)
    seen = []
    checker.update_changed.connect(seen.append)
    return checker, seen


def run_check(checker) -> None:
    assert checker.check_now()
    assert wait_for(lambda: checker._worker is None)


def test_a_newer_release_is_offered(qapp, settings):
    fetch = FakeFetch((200, release_json("v1.5.0"), '"e1"'))
    checker, seen = make_checker(settings, fetch, Clock())
    run_check(checker)
    assert [r.version for r in seen] == ["1.5.0"]
    assert fetch.threads[0] is not threading.main_thread(), "fetched on the UI thread"
    state = settings.get("update_check")
    assert state["etag"] == '"e1"' and state["latest"]["version"] == "1.5.0"


@pytest.mark.parametrize("tag", ["v1.4.0", "v1.3.0", "1.0.0"])
def test_nothing_is_offered_when_this_copy_is_current(qapp, settings, tag):
    """The real state of this line today: latest is v1.3.0, this is 1.4.0."""
    checker, seen = make_checker(settings, FakeFetch((200, release_json(tag), "")), Clock())
    run_check(checker)
    assert seen == [] and checker.available() is None


@pytest.mark.parametrize("failure", [
    FetchError("unreachable"), FetchError("HTTP 500"), FetchError("malformed"),
    RuntimeError("a bug in the fetch"),
])
def test_failures_are_silent_and_still_count_as_the_hours_check(qapp, settings, failure):
    clock = Clock()
    fetch = FakeFetch(failure)
    checker, seen = make_checker(settings, fetch, clock)
    run_check(checker)
    assert seen == []
    assert settings.get("update_check")["checked_at"] == clock.now
    assert not checker.check_now(), "a failed check was retried at once"
    assert len(fetch.calls) == 1


def test_a_missing_field_payload_offers_nothing(qapp, settings):
    checker, seen = make_checker(settings, FakeFetch((200, {}, "")), Clock())
    run_check(checker)
    assert seen == []


def test_at_most_once_an_hour_even_across_restarts(qapp, settings):
    clock = Clock()
    fetch = FakeFetch((200, release_json("v1.5.0"), ""), (200, release_json("v1.6.0"), ""))
    first, _ = make_checker(settings, fetch, clock)
    run_check(first)
    # "Restart": a new checker over the same stored settings.
    second, seen = make_checker(settings, fetch, clock)
    assert not second.check_now()
    assert len(fetch.calls) == 1
    clock.now += u.CHECK_INTERVAL_S + 1
    run_check(second)
    assert [r.version for r in seen] == ["1.6.0"]


def test_rate_limiting_moves_the_next_check(qapp, settings):
    clock = Clock()
    fetch = FakeFetch(FetchError("HTTP 403", retry_at=clock.now + 3 * 3600))
    checker, _ = make_checker(settings, fetch, clock)
    run_check(checker)
    clock.now += u.CHECK_INTERVAL_S + 1
    assert checker.seconds_until_due() > 3600, "the reset time was ignored"


def test_an_unchanged_answer_reuses_what_was_stored(qapp, settings):
    clock = Clock()
    fetch = FakeFetch((200, release_json("v1.5.0"), '"e1"'), (304, None, '"e1"'))
    checker, seen = make_checker(settings, fetch, clock)
    run_check(checker)
    clock.now += u.CHECK_INTERVAL_S + 1
    run_check(checker)
    assert fetch.calls[1][1] == '"e1"', "the ETag was not sent"
    assert checker.available().version == "1.5.0"


def test_a_remembered_update_is_offered_at_start_without_the_network(qapp, settings):
    settings.set("update_check", {
        "checked_at": 1_900_000_000.0,
        "latest": Release("v1.5.0", "1.5.0",
                          "https://github.com/preinfection/unified/releases/tag/v1.5.0",
                          "", "", "").to_json(),
    })
    fetch = FakeFetch()
    checker, seen = make_checker(settings, fetch, Clock())
    checker.start()
    assert [r.version for r in seen] == ["1.5.0"]
    assert fetch.calls == []
    assert checker.next_check_in() >= u.FIRST_CHECK_DELAY_S - 1, "checked during startup"
    checker.shutdown()


def test_the_first_check_waits_for_startup_to_finish(qapp, settings):
    checker, _ = make_checker(settings, FakeFetch(), Clock())
    checker.start()
    assert checker.next_check_in() >= u.FIRST_CHECK_DELAY_S - 1
    checker.shutdown()


def test_updating_the_app_retires_the_offer(qapp, settings):
    settings.set("update_check", {"checked_at": 0, "latest": Release(
        "v1.5.0", "1.5.0",
        "https://github.com/preinfection/unified/releases/tag/v1.5.0", "", "", "",
    ).to_json()})
    checker, seen = make_checker(settings, FakeFetch(), Clock(), current="1.5.0")
    checker.start()
    assert seen == [] and checker.available() is None
    checker.shutdown()


# ============================================================ update button

@pytest.fixture()
def band(qapp):
    from app.ui.components.toolbar import TopToolBar
    from app.ui.components.update_button import UpdateButton

    bar = TopToolBar()
    button = UpdateButton()
    bar.add_trailing(button)
    bar.resize(1440, t.TOOLBAR_HEIGHT)
    bar.show()
    qapp.processEvents()
    yield bar, button
    bar.close()
    motion.set_motion_enabled(True)


NEWER = Release("v1.5.0", "1.5.0",
                "https://github.com/preinfection/unified/releases/tag/v1.5.0", "", "", "")


def test_no_update_means_no_button_and_no_gap(band, qapp):
    from app.ui.components.toolbar import TopToolBar

    bar, button = band
    assert button.isHidden()
    plain = TopToolBar()
    plain.resize(1440, t.TOOLBAR_HEIGHT)
    plain.show()
    qapp.processEvents()
    assert bar.refresh_btn.geometry() == plain.refresh_btn.geometry()
    assert bar.search_edit.geometry() == plain.search_edit.geometry()
    assert bar.dock.geometry() == plain.dock.geometry()
    plain.close()


def test_an_update_shows_a_labelled_button_that_fits(band, qapp):
    bar, button = band
    button.set_release(NEWER)
    bar.relayout()
    assert not button.isHidden()
    assert button.text() == "Update"
    assert "1.5.0" in button.toolTip() and "1.5.0" in button.accessibleName()
    for width in (1440, 1000, 820):
        bar.resize(width, t.TOOLBAR_HEIGHT)
        qapp.processEvents()
        rects = [bar.search_edit.geometry(), bar.dock.geometry(),
                 button.geometry(), bar.refresh_btn.geometry()]
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                assert not a.intersects(b), f"{a} overlaps {b} at {width}"
    button.set_release(None)
    assert button.isHidden()


def test_the_button_opens_exactly_the_release_page(band, monkeypatch):
    from app.ui.components import update_button as module

    opened = []
    monkeypatch.setattr(module.QDesktopServices, "openUrl",
                        lambda url: opened.append(url.toString()))
    bar, button = band
    button.set_release(NEWER)
    button.click()
    assert opened == [NEWER.url]


def test_a_foreign_url_is_never_offered(band):
    bar, button = band
    button.set_release(Release("v9.0.0", "9.0.0", "https://evil.example/x", "", "", ""))
    assert button.isHidden()


def test_the_shine_crosses_once_and_never_loops(band, qapp):
    motion.set_motion_enabled(True)
    bar, button = band
    button.set_release(NEWER)
    assert button.is_shining(), "no glint when the update arrived"
    assert wait_for(lambda: not button.is_shining(), 2500)
    loop = QEventLoop()
    QTimer.singleShot(400, loop.quit)
    loop.exec()
    assert not button.is_shining(), "the shine started again on its own"


def test_no_shine_under_reduced_motion(band):
    motion.set_motion_enabled(False)
    bar, button = band
    button.set_release(NEWER)
    assert not button.is_shining()
    assert not button.play_shine()


# ================================================================ changelog

def test_release_notes_render_only_a_safe_subset():
    from app.ui.components.changelog import render_markdown

    md = (
        "# Unified v1.5.0\n\nIntro line one\ncontinues here.\n\n"
        "## Fixed\n\n- **Bold** and *italic* and `code`\n"
        "◉ A glyph bullet\n\n"
        "![pixel](https://tracker.example/p.gif)\n"
        '<img src="https://tracker.example/q.gif"><script>alert(1)</script>\n'
        "See [the issue](https://github.com/x/y/issues/1) and <https://example.com>.\n"
        "5 < 6 & <b>not bold</b>\n"
    )
    release = Release("v1.5.0", "1.5.0", "https://github.com/preinfection/unified/releases/tag/v1.5.0", "", "", md)
    out = render_markdown(md, release)
    assert "<h" not in out.split("</p>")[0], "the heading restating the version stayed"
    assert "<p>Intro line one continues here.</p>" in out
    assert "<b>Bold</b>" in out and "<i>italic</i>" in out and "<code>code</code>" in out
    assert out.count("<li>") == 2
    assert "tracker.example" not in out, "an image survived"
    assert "<script" not in out and "<img" not in out
    assert "href" not in out and "the issue" in out
    assert "5 &lt; 6 &amp;" in out


def test_a_quoted_note_shows_as_text_without_its_markers():
    from app.ui.components.changelog import render_markdown

    out = render_markdown("> **Note.** One line\n> and the next.\n>\n> - a point\n\nAfter.\n")
    assert "&gt;" not in out, "a quote marker was drawn as text"
    assert "<p><b>Note.</b> One line and the next.</p>" in out
    assert out.count("<li>") == 1 and "<p>After.</p>" in out


@pytest.fixture()
def notes_path(tmp_path):
    return tmp_path / "release_notes.json"


def test_the_store_loads_then_caches(qapp, notes_path):
    clock = Clock()
    fetch = FakeFetch((200, [release_json("v1.5.0"), release_json("1.4.0")], '"l1"'))
    store = ReleaseNotesStore(notes_path, fetch=fetch, clock=clock)
    states = []
    store.changed.connect(lambda releases, status: states.append((len(releases), status)))
    store.refresh()
    assert wait_for(lambda: store.status == "fresh")
    assert states == [(0, "loading"), (2, "fresh")]
    # A second store (the next launch) reads the disk copy and does not ask.
    again = ReleaseNotesStore(notes_path, fetch=fetch, clock=clock)
    again.refresh()
    assert again.status == "cached" and len(fetch.calls) == 1


def test_a_failed_refresh_keeps_the_saved_notes(qapp, notes_path):
    clock = Clock()
    fetch = FakeFetch((200, [release_json("v1.5.0")], ""), FetchError("offline"))
    store = ReleaseNotesStore(notes_path, fetch=fetch, clock=clock)
    store.refresh()
    assert wait_for(lambda: store.status == "fresh")
    clock.now += u.CHECK_INTERVAL_S + 1
    store.refresh()
    assert wait_for(lambda: store.status == "stale")
    assert [r.version for r in store.releases] == ["1.5.0"]


@pytest.mark.parametrize("result, status", [
    (FetchError("offline"), "failed"),
    ((200, [], ""), "empty"),
    ((200, {"message": "Not Found"}, ""), "failed"),
])
def test_first_load_outcomes(qapp, notes_path, result, status):
    store = ReleaseNotesStore(notes_path, fetch=FakeFetch(result), clock=Clock())
    store.refresh()
    assert wait_for(lambda: store.status == status), store.status


def test_the_page_lists_newest_first_and_marks_this_copy(qapp, notes_path):
    from app.ui.components.changelog import ChangelogPage

    fetch = FakeFetch((200, [release_json("1.3.0"), release_json("v1.5.0"),
                             release_json("1.4.0")], ""))
    store = ReleaseNotesStore(notes_path, fetch=fetch, clock=Clock())
    page = ChangelogPage(store, current="1.4.0")
    assert fetch.calls == [], "the network was asked before the page was opened"
    assert "Loading" in page.status.text()
    page.resize(700, 500)
    page.show()
    assert wait_for(lambda: len(page.entries) == 3)
    assert [e.release.version for e in page.entries] == ["1.5.0", "1.4.0", "1.3.0"]
    markers = [e.marker.text() for e in page.entries]
    assert markers == ["Newer", "Your version", ""]
    assert "v1.4.0" in page.status.text()
    page.close()


def test_the_page_says_so_when_it_cannot_load(qapp, notes_path):
    from app.ui.components.changelog import ChangelogPage

    store = ReleaseNotesStore(notes_path, fetch=FakeFetch(FetchError("offline")),
                              clock=Clock())
    page = ChangelogPage(store)
    page.show()
    assert wait_for(lambda: store.status == "failed")
    assert "could not be loaded" in page.status.text()
    assert page.entries == []
    page.close()


def test_settings_has_a_changelog_entry(qapp, settings, tmp_path):
    from app.database import Database
    from app.services.account_manager import AccountManager
    from app.ui.settings_dialog import SettingsDialog

    db = Database(tmp_path / "m.db")
    store = ReleaseNotesStore(tmp_path / "notes.json", fetch=FakeFetch(), clock=Clock())
    dialog = SettingsDialog(settings, AccountManager(db), release_notes=store)
    labels = [b.text() for b in dialog._rail_group.buttons()]
    assert labels[-1] == "Changelog"
    assert dialog.stack.count() == len(labels)
    db.close()
