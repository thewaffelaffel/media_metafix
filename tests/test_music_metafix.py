from argparse import Namespace

from conftest import write_queue


def test_track_parsing(mmf):
    assert mmf.track_number_from_filename("03 - Song") == 3
    assert mmf.track_number_from_filename("Track 7") == 7
    assert mmf.track_number_from_filename("1999") is None
    assert mmf.strip_filename_track_prefix("03 - Song") == "Song"


def test_render_filename(mmf, tmp_path):
    tags = {"tracknumber": "3/12", "title": "Song",
            "artists": ["A", "B", "C"]}
    name = mmf.render_filename(
        "%num - %title (feat. %features)", tmp_path / "x.mp3", tags,
    )
    assert name == "03 - Song (feat. B, C).mp3"


def test_strip_title_variations(mmf):
    assert mmf.strip_title_variations(
        "Song (feat. X) - Remastered 2011") == "Song"


def test_check_track_warnings(mmf, tmp_path, answer, capsys):
    queue = write_queue(tmp_path / "q.yml", (
        "A/B/01 - One.mp3:\n  album: B\n  artist: A\n"
        "  artists: [A]\n  title: One\n  tracknumber: 1\n"
        "A/B/03 - Three.mp3:\n  album: C\n  artist: A\n"
        "  artists: [Z]\n  title: One\n  tracknumber: 3\n"
    ))
    answer("2")
    mmf.run_check_step(Namespace(queue=queue))
    out = capsys.readouterr().out
    assert "track number(s) 2 missing" in out
    assert "same title 'One'" in out
    assert "disagree on album" in out
    assert "doesn't match the first entry in artists" in out
