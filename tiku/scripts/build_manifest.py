#!/usr/bin/env python3
"""Rebuild manifest.json from the .json files found under a folder.

The folder holding the .json files is supplied on the command line as a path
relative to the repository root (or typed at the prompt when it is omitted). The
manifest is always written to the repository root as manifest.json, and every
listed path is relative to that root too, so the manifest stays a valid index of
the repository no matter how deeply the files are nested.

The file list is rebuilt from disk on every run, so entries whose file has been
deleted or renamed are dropped automatically, as is a `default` that points at a
file that no longer exists. The manifest is rewritten even when nothing is left,
so a fully emptied folder cannot leave stale entries behind. Every run reports
what it removed and added.

    {
      "default": { "chapter": "ExampleChapter", "file": "Example.json" },
      "files": ["ExampleChapter/Example.json", ...]
    }

Usage:
    python3 scripts/build_manifest.py assets
    python3 scripts/build_manifest.py data/questions
    python3 scripts/build_manifest.py assets --default chapter2/test2_2.json
    python3 scripts/build_manifest.py assets --default test2_2.json
    python3 scripts/build_manifest.py assets --clear-default

--default takes a path as listed in the manifest, or just the bare file name when
that name is unique. Without --default, an existing default is kept only while
its file still exists; otherwise the default is removed and the webpage opens the
first file.
"""

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "manifest.json"


def split_path(path: str) -> tuple[str, str]:
    """'FudanFreshman26/26-1-name.json' -> ('FudanFreshman26', '26-1-name.json');
    a file listed at the repository root -> ('', name)."""
    head, sep, tail = path.partition("/")
    return (head, tail) if sep else ("", head)


def as_path(default: dict) -> str:
    chapter = default["chapter"]
    return f"{chapter}/{default['file']}" if chapter else default["file"]


def resolve_folder(raw: str) -> pathlib.Path | None:
    """The .json folder, as ROOT / <given path>. None if the path escapes ROOT."""
    given = pathlib.Path(raw).expanduser()
    folder = (given if given.is_absolute() else ROOT / given).resolve()
    if folder != ROOT and ROOT not in folder.parents:
        return None
    return folder


def as_listed(raw: str, files: list[str], assets: pathlib.Path) -> str | None:
    """The --default path as the manifest lists it, or None when it names no file.

    Three spellings are accepted, because the listed paths are root-relative and
    the folder argument is typed separately: the listed path itself, the same path
    without the folder prefix, and a bare file name while it is unambiguous.
    """
    given = raw.strip()
    # Strip a single leading './' without disturbing '../' or dotfile names.
    if given.startswith("./"):
        given = given[2:]

    prefix = assets.relative_to(ROOT).as_posix()
    candidates = [given]
    if prefix != "." and not given.startswith(f"{prefix}/"):
        candidates.insert(0, f"{prefix}/{given}")

    for candidate in candidates:
        if candidate in files:
            return candidate

    by_name = [p for p in files if p.rsplit("/", 1)[-1] == given]
    return by_name[0] if len(by_name) == 1 else None


def ask_for_folder() -> str:
    """The folder path, from the prompt or a piped line of input."""
    prompt = "folder of .json files, relative to the repository root: "
    if sys.stdin is not None and sys.stdin.isatty():
        return input(prompt)
    print(prompt, end="", flush=True, file=sys.stderr)
    return sys.stdin.readline()


def read_previous(manifest: pathlib.Path) -> tuple[list[str], dict | None]:
    """The manifest currently on disk, as (files, default).

    Tolerant of a missing, unreadable or legacy manifest: a bare JSON array is
    read as the file list.
    """
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], None

    if isinstance(data, list):
        listed = data
        default = None
    elif isinstance(data, dict):
        listed = data.get("files")
        default = data.get("default")
    else:
        return [], None

    files = [p for p in listed if isinstance(p, str)] if isinstance(listed, list) else []

    if not isinstance(default, dict):
        default = None
    else:
        chapter, file = default.get("chapter"), default.get("file")
        if not (isinstance(chapter, str) and isinstance(file, str)):
            default = None
        else:
            default = {"chapter": chapter, "file": file}

    return files, default


def scan_assets(assets: pathlib.Path) -> list[str]:
    """Every .json under the folder, as a root-relative sorted path.

    Only .json files are trusted, and manifest.json is never listed: it is this
    repo's index name, so a stale copy left inside the folder - the output of the
    earlier in-folder layout - must not come back as a data entry.
    """
    return sorted(
        p.relative_to(ROOT).as_posix()
        for p in assets.rglob("*.json")
        if p.is_file() and p.name != MANIFEST.name
    )


def report(removed: list[str], added: list[str], default: dict | None, note: str) -> None:
    if removed:
        word = "entry" if len(removed) == 1 else "entries"
        print(f"\n{len(removed)} {word} removed (no longer on disk):")
        for path in removed:
            print(f"  - {path}")
    if added:
        word = "entry" if len(added) == 1 else "entries"
        print(f"\n{len(added)} {word} added:")
        for path in added:
            print(f"  - {path}")

    print(f"\ndefault: {as_path(default) if default else '(none)'} ({note})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", metavar="FOLDER",
                        help="folder holding the .json files, relative to the repository "
                             "root; prompted for when omitted")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--default", metavar="PATH",
                       help="file to open by default, e.g. FudanFreshman26/26-1-name.json, "
                            "or a bare file name when it is unique")
    group.add_argument("--clear-default", action="store_true",
                       help="do not record a default file")
    args = parser.parse_args()

    raw = args.folder if args.folder is not None else ask_for_folder()
    if not raw.strip():
        print("error: no folder given", file=sys.stderr)
        return 1

    assets = resolve_folder(raw.strip())
    if assets is None:
        print(f"error: {raw.strip()!r} is outside {ROOT}", file=sys.stderr)
        return 1
    if assets == ROOT:
        print(f"error: give the folder holding the .json files, not {ROOT} itself",
              file=sys.stderr)
        return 1

    if not assets.is_dir():
        print(f"error: {assets} does not exist", file=sys.stderr)
        return 1

    previous_files, previous_default = read_previous(MANIFEST)
    files = scan_assets(assets)
    on_disk = set(files)

    removed = [p for p in previous_files if p not in on_disk]
    added = [p for p in files if p not in set(previous_files)]

    # Work out the default. A default whose file is gone is removed, never
    # silently repointed at an unrelated file.
    if args.clear_default:
        default, note = None, "cleared on request"
    elif args.default:
        requested = as_listed(args.default, files, assets)
        if requested is None:
            print(f"error: {args.default.strip()!r} is not one of the known files:",
                  file=sys.stderr)
            for name in files:
                print(f"  - {name}", file=sys.stderr)
            return 1
        chapter, name = split_path(requested)
        default, note = {"chapter": chapter, "file": name}, "set on request"
    elif previous_default is None:
        default, note = None, "none recorded"
    elif as_path(previous_default) in on_disk:
        default, note = previous_default, "kept, its file still exists"
    else:
        default, note = None, f"was {as_path(previous_default)!r}, no longer exists - removed"

    payload: dict = {}
    if default is not None:
        payload["default"] = default
    payload["files"] = files

    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {MANIFEST.relative_to(ROOT)} with {len(files)} file(s):")
    for name in files:
        marker = "  <- default" if default and as_path(default) == name else ""
        print(f"  - {name}{marker}")

    if not files:
        print(f"warning: no .json files found under {assets} - the file list is now empty",
              file=sys.stderr)

    report(removed, added, default, note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
