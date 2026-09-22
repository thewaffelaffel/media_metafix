"""TVmaze, TMDB and OpenSubtitles code, with HTTP faked out."""

from argparse import Namespace
from urllib.error import HTTPError

import pytest

from conftest import make_video, needs_ffmpeg, write_queue

SRT = b"1\n00:00:00,000 --> 00:00:00,500\nHello\n"
EPISODES = {
    "name": "The Office",
    "_embedded": {"episodes": [
        {"season": 1, "number": 1, "name": "Pilot"},
        {"season": 1, "number": 2, "name": "Diversity Day"},
        {"season": 0, "number": None, "name": "Unnumbered special"},
    ]},
}


class FakeApi:
    """Stands in for fetch_json/fetch, answering by URL suffix and
    recording every call as (url, params, headers, body)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def fetch_json(self, url, params=None, headers=None, body=None):
        self.calls.append((url, params or {}, headers or {}, body))
        for suffix, respond in self.routes.items():
            if url.endswith(suffix):
                return respond(params or {}, body)
        raise AssertionError(f"unexpected request to {url}")

    def fetch(self, url, params=None, headers=None, body=None):
        self.calls.append((url, params or {}, headers or {}, body))
        return SRT

    def requests_to(self, suffix):
        return [c for c in self.calls if c[0].endswith(suffix)]


@pytest.fixture
def fake_api(tmf, monkeypatch):
    def install(**routes):
        api = FakeApi({
            "/" + name.replace("_", "/"): respond
            for name, respond in routes.items()
        })
        monkeypatch.setattr(tmf, "fetch_json", api.fetch_json)
        monkeypatch.setattr(tmf, "fetch", api.fetch)
        return api
    return install


def not_found(*_args):
    raise HTTPError("url", 404, "Not Found", {}, None)


def subtitle(file_id, hash_match=False, downloads=1, **feature):
    return {"attributes": {
        "moviehash_match": hash_match, "download_count": downloads,
        "files": [{"file_id": file_id}], "feature_details": feature,
    }}


# ---------------------------------------------------------------------------
# Metadata lookups
# ---------------------------------------------------------------------------

def test_tvmaze_episodes(tmf, fake_api):
    api = fake_api(shows=lambda params, body: EPISODES)
    name, titles = tmf.tvmaze_episodes("the office")
    assert name == "The Office"
    assert titles == {(1, 1): "Pilot", (1, 2): "Diversity Day"}
    _url, params, headers, _body = api.calls[0]
    assert params == {"q": "the office", "embed": "episodes"}
    assert headers["User-Agent"] == tmf.USER_AGENT


def test_tvmaze_unknown_show(tmf, fake_api):
    fake_api(shows=not_found)
    assert tmf.tvmaze_episodes("nope") is None


def test_show_episodes_warns_on_other_show(tmf, fake_api, capsys):
    api = fake_api(shows=lambda params, body: EPISODES)
    args = Namespace(no_tvmaze=False)
    cache = {}
    assert tmf.show_episodes("Office", args, cache)[(1, 1)] == "Pilot"
    assert "TVmaze matched 'The Office' for folder 'Office'" in \
        capsys.readouterr().err
    assert tmf.show_episodes("Office", args, cache)
    assert len(api.calls) == 1  # cached


def test_lookup_failure_is_cached_as_none(tmf, fake_api, capsys):
    def server_error(*_args):
        raise HTTPError("url", 500, "Oops", {}, None)
    api = fake_api(shows=server_error)
    args, cache = Namespace(no_tvmaze=False), {}
    assert tmf.show_episodes("X", args, cache) is None
    assert tmf.show_episodes("X", args, cache) is None
    assert len(api.calls) == 1
    assert "TVmaze lookup for 'X' failed" in capsys.readouterr().err


def test_tmdb_movie(tmf, fake_api):
    api = fake_api(movie=lambda params, body: {"results": [
        {"title": "Heat", "release_date": "1995-12-15"},
        {"title": "Heat 2", "release_date": ""},
    ]})
    assert tmf.tmdb_movie("heat", 1995, "key") == {
        "title": "Heat", "year": 1995,
    }
    assert api.calls[0][1] == {"query": "heat", "api_key": "key",
                               "year": 1995}


def test_tmdb_no_results(tmf, fake_api):
    api = fake_api(movie=lambda params, body: {"results": []})
    assert tmf.tmdb_movie("zzz", None, "key") is None
    assert "year" not in api.calls[0][1]


@needs_ffmpeg
def test_scan_uses_tmdb(tmf, fake_api, tmp_path):
    fake_api(movie=lambda params, body: {"results": [{
        "title": "Harry Potter and the Philosopher's Stone",
        "release_date": "2001-11-16",
    }]})
    root = tmp_path / "root"
    make_video(root / "Harry Potter" / "Sorcerers Stone (2001).mkv")
    queue = tmp_path / "q.yml"
    tmf.run_scan(Namespace(
        root=str(root), queue=str(queue), tmdb_api_key="key",
        no_tvmaze=True,
    ))
    assert tmf.load_queue(queue) == {
        "Harry Potter/Sorcerers Stone (2001).mkv": {
            "series": "Harry Potter",
            "title": "Harry Potter and the Philosopher's Stone",
            "year": 2001,
        },
    }


# ---------------------------------------------------------------------------
# OpenSubtitles client
# ---------------------------------------------------------------------------

def test_opensubtitles_login_search_download(tmf, fake_api):
    api = fake_api(
        login=lambda params, body: {"token": "tok"},
        subtitles=lambda params, body: {"data": [subtitle(7)]},
        download=lambda params, body: {"link": "https://dl.example/7"},
    )
    client = tmf.OpenSubtitles("key")
    client.login("user", "pass")
    results = client.search(languages="en", year=None, query="Heat")
    assert client.download(7) == SRT

    login, search, download, link = api.calls
    assert login[3] == {"username": "user", "password": "pass"}
    assert login[2]["Api-Key"] == "key"
    assert "Authorization" not in login[2]
    assert search[1] == {"languages": "en", "query": "Heat"}
    assert search[2]["Authorization"] == "Bearer tok"
    assert results[0]["attributes"]["files"] == [{"file_id": 7}]
    assert download[3] == {"file_id": 7}
    assert link[0] == "https://dl.example/7"


def test_opensubtitles_client_needs_key(tmf, capsys):
    assert tmf.opensubtitles_client(
        Namespace(opensubtitles_api_key=None)) is None
    assert "no OpenSubtitles API key" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------

def big_file(path, seed=0):
    """Large enough to hash (two 64 KiB chunks); `seed` varies it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes([seed]) + bytes(range(256)) * 1024)
    return path


def test_fingerprint(tmf, fake_api, tmp_path, capsys):
    root = tmp_path / "root"
    known = {
        "Show/S1/a.mkv": [subtitle(1, hash_match=True, title="Pilot",
                                   season_number=1, episode_number=1)],
        "Show/S1/b.mkv": [subtitle(2, hash_match=True, title="Pilot",
                                   season_number=1, episode_number=1)],
        "Show/S1/c.mkv": [subtitle(3, title="Pilot")],  # no hash match
    }
    hashes = {}
    for seed, file in enumerate(known):
        hashes[tmf.oshash(big_file(root / file, seed))] = known[file]
    hashes[tmf.oshash(big_file(root / "Heat" / "Heat.mkv", 9))] = [
        subtitle(4, hash_match=True, title="Heat", year=1995)]
    api = fake_api(subtitles=lambda params, body: {
        "data": hashes[params["moviehash"]],
    })
    queue = write_queue(tmp_path / "q.yml", (
        "Show/S1/a.mkv: {season: 1, episode: 1, title: Pilot}\n"
        "Show/S1/b.mkv: {season: 1, episode: 2, title: Two}\n"
        "Show/S1/c.mkv: {season: 1, episode: 3, title: Three}\n"
        "Heat/Heat.mkv: {title: Heat, year: 1995}\n"
        "Gone/Gone.mkv: {title: Gone}\n"
    ))
    tmf.run_fingerprint(Namespace(
        root=str(root), queue=str(queue), opensubtitles_api_key="key",
    ))
    out, err = capsys.readouterr()
    assert "Show/S1/b.mkv: queued entry doesn't match" in err
    assert "S1E1 'Pilot'" in err
    assert "Show/S1/a.mkv" not in err
    assert "File not found" in err
    assert ("3 file(s) identified, 1 mismatch(es), 1 unknown, "
            "1 skipped.") in out
    assert len(api.requests_to("/subtitles")) == 4


def test_fingerprint_lookup_error_skips(tmf, fake_api, tmp_path, capsys):
    def server_error(*_args):
        raise HTTPError("url", 503, "Down", {}, None)
    fake_api(subtitles=server_error)
    root = tmp_path / "root"
    big_file(root / "Heat" / "Heat.mkv")
    queue = write_queue(tmp_path / "q.yml", "Heat/Heat.mkv: {title: H}\n")
    tmf.run_fingerprint(Namespace(
        root=str(root), queue=str(queue), opensubtitles_api_key="key",
    ))
    assert "Hash lookup failed" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# caption
# ---------------------------------------------------------------------------

def test_find_subtitle_prefers_hash_match(tmf, fake_api, monkeypatch):
    monkeypatch.setattr(tmf, "oshash", lambda path: "abc")
    api = fake_api(subtitles=lambda params, body: {"data": [
        subtitle(1, downloads=99), subtitle(2, hash_match=True),
    ]})
    assert tmf.find_subtitle(tmf.OpenSubtitles("k"), None, None, "en") == 2
    # A hash match means no fallback text search.
    assert len(api.calls) == 1
    assert api.calls[0][1] == {"languages": "en", "moviehash": "abc"}


@needs_ffmpeg
def test_caption(tmf, fake_api, tmp_path, capsys):
    root = tmp_path / "root"
    episode = make_video(root / "Show" / "Season 2" / "S02E05 - X.mkv")
    movie = make_video(root / "Heat" / "Heat (1995).avi")
    api = fake_api(
        subtitles=lambda params, body: {
            "data": [] if "moviehash" in params else [subtitle(9)],
        },
        download=lambda params, body: {"link": "https://dl.example/9"},
    )
    args = Namespace(
        root=str(root), lang="en", opensubtitles_api_key="key",
        opensubtitles_username=None, dry_run=False,
    )
    tmf.run_caption(args)
    assert "2 captioned" in capsys.readouterr().out
    assert tmf.has_subtitles(episode, "en")
    assert (movie.parent / "Heat (1995).en.srt").read_bytes() == SRT

    searches = [c[1] for c in api.requests_to("/subtitles")
                if "query" in c[1]]
    assert {"languages": "en", "query": "Heat", "year": 1995,
            "type": "movie"} in searches
    assert {"languages": "en", "query": "Show", "season_number": 2,
            "episode_number": 5, "type": "episode"} in searches

    api.calls.clear()
    tmf.run_caption(args)
    assert "2 already had subtitles" in capsys.readouterr().out
    assert api.calls == []


@needs_ffmpeg
def test_caption_not_found(tmf, fake_api, tmp_path, capsys):
    root = tmp_path / "root"
    make_video(root / "Heat" / "Heat.mkv")
    fake_api(subtitles=lambda params, body: {"data": []})
    tmf.run_caption(Namespace(
        root=str(root), lang="fr", opensubtitles_api_key="key",
        opensubtitles_username=None, dry_run=False,
    ))
    out, err = capsys.readouterr()
    assert "No fr subtitles found" in err
    assert "1 not found" in out


@needs_ffmpeg
def test_caption_dry_run_skips_download(tmf, fake_api, tmp_path, capsys):
    root = tmp_path / "root"
    movie = make_video(root / "Heat" / "Heat.mkv")
    api = fake_api(subtitles=lambda params, body: {"data": [subtitle(9)]})
    tmf.run_caption(Namespace(
        root=str(root), lang="en", opensubtitles_api_key="key",
        opensubtitles_username=None, dry_run=True,
    ))
    assert f"Would caption: {movie}" in capsys.readouterr().out
    assert api.requests_to("/download") == []
    assert not tmf.has_subtitles(movie, "en")
