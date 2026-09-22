# media_metafix

Two scripts that check and fix media library metadata:

- **`music_metafix`** (MMF): music laid out as `root/artist/album/song.ext`.
- **`tv_metafix`** (TMF): TV shows as `root/show/season/episode.ext` and
  movies as `root/series/title.ext` (e.g. `Harry Potter/Harry Potter and
  the Sorcerer's Stone (2001).mkv`). One root can hold both.

Folder names are trusted (artist/album, show/season, series). The rest
comes from online lookups.

## Setup

```sh
sudo apt install ffmpeg libchromaprint-tools   # chromaprint: MMF only
pip install pyyaml pathspec                    # both scripts
pip install mutagen pyacoustid musicbrainzngs pillow   # MMF only
```

Free API keys (optional; each one enables the steps listed):

| Variable                        | Used by               | Get one at                          |
|---------------------------------|-----------------------|-------------------------------------|
| `MMF_ACOUSTID_API_KEY`          | MMF `fingerprint`     | acoustid.org/new-application        |
| `MMF_MUSICBRAINZ_CONTACT`       | MMF `scan`            | (your email)                        |
| `TMF_TMDB_API_KEY`              | TMF `scan` (movies)   | themoviedb.org/settings/api         |
| `TMF_OPENSUBTITLES_API_KEY`     | TMF `fingerprint`, `caption` | opensubtitles.com/consumers  |
| `TMF_OPENSUBTITLES_USERNAME`/`_PASSWORD` | TMF `caption` (higher download limit) | opensubtitles.com |

## Workflow

Both scripts follow the same scan → check → apply loop:

```sh
tv_metafix scan /videos          # look up metadata, write tmp/changes.yml
tv_metafix check                 # flag suspicious entries interactively
tv_metafix fingerprint /videos   # optional: compare against the files
tv_metafix apply /videos         # write the (edited) queue to disk
```

`scan` never touches your files. It writes a YAML queue to review and
edit. In the queue, delete a field to skip that change, or delete an
entry to skip that file. `check` warns about things like duplicate or
missing track/episode numbers, filenames that don't match the new
number or title, and fields that are blank or disagree within a folder.
For each warning you can edit the queue, skip it, or mark it `# OK` so
it isn't flagged again.

Other steps:

| MMF                                  | TMF                                       |
|--------------------------------------|-------------------------------------------|
| `normalize <root>` (loudness)        | `caption <root> [--lang en]` (subtitles)  |
| `convert <root> wma mp3` (re-encode) | `convert <root> avi mkv` (remux)          |
| `rename <root> "%num - %title"`      | `rename <root> --episodes "S%seasonE%episode - %title" --movies "%title (%year)"` |

Run any step with `-h` for its options.

### Where the data comes from

- **MMF**: MusicBrainz (titles and track numbers), Cover Art Archive
  (album art), AcoustID (`fingerprint`).
- **TMF**: [TVmaze](https://www.tvmaze.com/api) (episodes, no key
  needed), [TMDB](https://developer.themoviedb.org) (movies; without a
  key, movie titles and years come from the filename, e.g.
  `Heat (1995).mkv`), and [OpenSubtitles](https://opensubtitles.com)
  (`caption`).
- **TMF `fingerprint`** looks each file up by its OpenSubtitles hash.
  There's no free perceptual video fingerprinting service, so this only
  identifies unmodified copies of releases that OpenSubtitles knows
  about. Re-encoded files show up as "unknown".
- **TMF `caption`** embeds subtitles in MKV, MP4, M4V, MOV and WebM
  files. For other containers such as AVI, it saves `name.<lang>.srt`
  next to the video instead. Files that already have subtitles in that
  language are skipped.

TMF stores tags with ffmpeg: `title`, `show`, `season_number`,
`episode_sort`, `date`, plus `collection` for the series (`album` in
MP4/AVI). AVI can't hold episode tags, so `apply` warns you to
`convert` those files to MKV.

### Safety

- Steps that modify files (`apply`, `normalize`, `caption`, `convert`,
  `rename`) first back up root to `tmp/backups/` unless you pass
  `--no-backup`. TMF backups are uncompressed `.tar` files, so budget
  disk space for large libraries.
- `tmp/` is relative to your current directory, not root. The queue
  records which root it was scanned from, and `apply` refuses to run
  against a different root.
- A `.mmfignore` file in root uses `.gitignore` syntax to exclude files
  and folders from every step, including backups.

## Layout

```
music_metafix, tv_metafix   the scripts
common/                     shared code: queue I/O, check framework,
                            .mmfignore/backups, ffmpeg, CLI helpers
tests/                      pytest suite: APIs are faked and network
                            access is blocked; ffmpeg tests skip
                            without ffmpeg
```

Run the tests with `pip install pytest && pytest tests`.
