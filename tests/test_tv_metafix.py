from argparse import Namespace
from pathlib import Path

import pytest

from conftest import make_video, needs_ffmpeg, write_queue


@pytest.mark.parametrize("name, season", [
    ("Season 2", 2), ("S03", 3), ("season_04", 4), ("7", 7),
    ("Specials", 0), ("Extras", None),
])
def test_season_from_dir(tmf, name, season):
    assert tmf.season_from_dir(name) == season


@pytest.mark.parametrize("stem, episode, title", [
    ("The Office - S01E03 - Health Care", 3, "Health Care"),
    ("show.1x12.Title", 12, "Title"),
    ("04 - The Alliance", 4, "The Alliance"),
    ("Episode 5", 5, ""),
    ("Pilot", None, "Pilot"),
])
def test_episode_parsing(tmf, stem, episode, title):
    assert tmf.episode_from_name(stem) == episode
    assert tmf.strip_episode_number(stem) == title


def test_movie_parsing(tmf):
    assert tmf.year_from_name("Heat (1995)") == 1995
    assert tmf.strip_year("Heat (1995)") == "Heat"
    assert tmf.year_from_name("Blade Runner 2049") is None


def test_guess_fields(tmf):
    assert tmf.guess_fields("Show/Season 1/S01E02 - Two.mkv") == {
        "show": "Show", "season": 1, "episode": 2, "title": "Two",
    }
    assert tmf.guess_fields("Harry Potter/Goblet (2005).mp4") == {
        "series": "Harry Potter", "title": "Goblet", "year": 2005,
    }


def test_iter_videos_mixed_root(tmf, tmp_path):
    for rel in ("Show/Season 1/e1.mkv", "Show/Season 1/notes.txt",
                "Movies/Heat (1995).mp4", "Skip/Season 1/e1.mkv",
                "Show/Season 1/deep/too-deep.mkv", "loose.mkv"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).touch()
    (tmp_path / ".mmfignore").write_text("Skip/\n")
    found = [
        p.relative_to(tmp_path).as_posix() for p in tmf.iter_videos(tmp_path)
    ]
    assert found == ["Movies/Heat (1995).mp4", "Show/Season 1/e1.mkv"]
    assert [tmf.kind_of(f) for f in found] == ["movie", "episode"]


def test_match_episode(tmf):
    titles = {(1, 1): "Pilot", (1, 2): "Diversity Day", (2, 1): "Pilot"}
    by_number = {"season": 1, "episode": 2, "title": "x"}
    by_title = {"season": 2, "episode": None, "title": "pilot"}
    assert tmf.match_episode(by_number, titles) == (1, 2, "Diversity Day")
    assert tmf.match_episode(by_title, titles) == (2, 1, "Pilot")


def test_oshash(tmf, tmp_path):
    path = tmp_path / "zeros.bin"
    path.write_bytes(bytes(131072))
    assert tmf.oshash(path) == "0000000000020000"
    path.write_bytes(b"\x01" + bytes(131071))
    assert tmf.oshash(path) == "0000000000020001"


def test_pick_subtitle_prefers_hash_match(tmf):
    def result(file_id, downloads, match=False):
        attributes = {
            "download_count": downloads, "moviehash_match": match,
            "files": [{"file_id": file_id}],
        }
        return {"attributes": attributes}
    results = [result(1, 900), result(2, 5, match=True), result(3, 50)]
    assert tmf.pick_subtitle(results) == 2
    assert tmf.pick_subtitle(results[::2]) == 1
    assert tmf.pick_subtitle([]) is None


def test_feature_agrees(tmf):
    feature = {"title": "Pilot", "season_number": 1, "episode_number": 1}
    episode = {"season": 1, "episode": 1, "title": "Pilot"}
    assert tmf.feature_agrees(feature, episode)
    assert not tmf.feature_agrees(feature, dict(episode, episode=2))
    assert tmf.feature_agrees({"title": "Heat"}, {"title": "Heat"})
    assert not tmf.feature_agrees({"title": "Heat"}, {"title": "Alien"})


def run_check(tmf, queue):
    return tmf.run_check(Namespace(queue=queue))


def test_check_episode_warnings(tmf, tmp_path, answer, capsys):
    queue = write_queue(tmp_path / "q.yml", (
        "Show/Season 1/S01E01 - Pilot.mkv:\n"
        "  show: Show\n  season: 1\n  episode: 1\n  title: Pilot\n"
        "Show/Season 1/S02E03 - Pilot.mkv:\n"
        "  show: Shoe\n  season: 1\n  episode: 1\n  title: Pilot\n"
    ))
    answer("2")
    run_check(tmf, queue)
    out = capsys.readouterr().out
    assert "same title 'Pilot'" in out
    assert "same episode number 1" in out
    assert "disagree on show" in out
    assert "filename says season 2, but season is 1" in out


def test_check_movie_warnings(tmf, tmp_path, answer, capsys):
    queue = write_queue(tmp_path / "q.yml", (
        "Heat/Heat (1995).mkv:\n  series: Heat\n  title: Heat\n"
        "  year: 1995\n"
        "Heat/Other.mkv:\n  series: Heat\n  title: ''\n  year: 3000\n"
    ))
    answer("2")
    run_check(tmf, queue)
    out = capsys.readouterr().out
    assert "Heat (1995)" not in out
    assert "title is blank" in out
    assert "year 3000 looks wrong" in out


@needs_ffmpeg
@pytest.mark.parametrize("ext", [".mkv", ".mp4", ".avi"])
def test_tag_round_trip(tmf, tmp_path, ext):
    path = make_video(tmp_path / f"v{ext}")
    fields = {"series": "Harry Potter", "title": "Goblet", "year": 2005}
    tmf.write_tags(path, fields)
    tags = tmf.read_tags(path)
    assert {k: tags[k] for k in fields} == fields


@needs_ffmpeg
def test_scan_and_apply(tmf, tmp_path, monkeypatch):
    root = tmp_path / "root"
    make_video(root / "Show" / "Season 1" / "02 - Wrong.mkv")
    make_video(root / "Heat" / "Heat (1995).mp4", "-metadata", "title=Heat")
    monkeypatch.setattr(tmf, "tvmaze_episodes", lambda show: (
        show, {(1, 2): "Diversity Day"},
    ))
    queue = tmp_path / "changes.yml"
    args = Namespace(
        root=str(root), queue=str(queue), tmdb_api_key=None,
        no_tvmaze=False, no_backup=True, tmp_dir=str(tmp_path),
    )
    tmf.run_scan(args)
    entries = tmf.load_queue(queue)
    movie = {"series": "Heat", "title": "Heat", "year": 1995}
    episode_fields = {
        "show": "Show", "season": 1, "episode": 2, "title": "Diversity Day",
    }
    assert entries == {
        "Heat/Heat (1995).mp4": movie,
        "Show/Season 1/02 - Wrong.mkv": episode_fields,
    }
    tmf.run_apply(args)
    episode = root / "Show" / "Season 1" / "02 - Wrong.mkv"
    assert tmf.read_tags(episode)["title"] == "Diversity Day"
    tmf.run_scan(args)
    assert tmf.load_queue(queue) == {}


@needs_ffmpeg
def test_embed_subtitle_and_rename(tmf, tmp_path):
    path = make_video(tmp_path / "Show" / "Season 1" / "e.mkv",
                      "-metadata", "title=Pilot",
                      "-metadata", "episode_sort=1",
                      "-metadata", "season_number=1")
    srt = b"1\n00:00:00,000 --> 00:00:00,500\nHi\n"
    assert tmf.save_subtitle(path, srt, "en") == path
    assert tmf.has_subtitles(path, "en")
    assert not tmf.has_subtitles(path, "fr")
    avi = make_video(tmp_path / "Movie" / "m.avi", "-metadata", "title=M")
    assert tmf.save_subtitle(avi, srt, "en") == Path(
        tmp_path / "Movie" / "m.en.srt")
    tmf.rename_file(path, "S%seasonE%episode %title")
    tmf.rename_file(avi, "%title (x)")
    assert (tmp_path / "Show" / "Season 1" / "S01E01 Pilot.mkv").exists()
    assert (tmp_path / "Movie" / "M (x).en.srt").exists()
