#!/usr/bin/env python3
"""Rebuild assets/manifest.json from the .json files found under assets/.

The file list is rebuilt from disk on every run, so entries whose file has been
deleted or renamed are dropped automatically, as is a `default` that points at a
file that no longer exists. The manifest is rewritten even when nothing is left,
so a fully emptied assets/ directory cannot leave stale entries behind. Every run
reports what it removed and added.

    {
      "default": { "chapter": "ExampleChapter", "file": "Example.json" },
      "files": ["ExampleChapter/Example.json", ...]
    }

Usage:
    python3 scripts/build_manifest.py
    python3 scripts/build_manifest.py --default chapter2/test2_2.json
    python3 scripts/build_manifest.py --clear-default

Without --default, an existing default is kept only while its file still exists;
otherwise the default is removed and the webpage opens the first file.
"""

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MANIFEST = ASSETS / "manifest.json"


def split_path(path: str) -> tuple[str, str]:
    """'chapter2/test2_2.json' -> ('chapter2', 'test2_2.json'); root file -> ('', name)."""
    head, sep, tail = path.partition("/")
    return (head, tail) if sep else ("", head)


def as_path(default: dict) -> str:
    chapter = default["chapter"]
    return f"{chapter}/{default['file']}" if chapter else default["file"]


def read_previous() -> tuple[list[str], dict | None]:
    """The manifest currently on disk, as (files, default).

    Tolerant of a missing, unreadable or legacy manifest: a bare JSON array is
    read as the file list.
    """
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
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


def scan_assets() -> list[str]:
    """Every .json under assets/, relative and sorted. Nothing else is trusted."""
    return sorted(
        p.relative_to(ASSETS).as_posix()
        for p in ASSETS.rglob("*.json")
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
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--default", metavar="PATH",
                       help="file to open by default, e.g. chapter2/test2_2.json")
    group.add_argument("--clear-default", action="store_true",
                       help="do not record a default file")
    args = parser.parse_args()

    if not ASSETS.is_dir():
        print(f"error: {ASSETS} does not exist", file=sys.stderr)
        return 1

    previous_files, previous_default = read_previous()
    files = scan_assets()
    on_disk = set(files)

    removed = [p for p in previous_files if p not in on_disk]
    added = [p for p in files if p not in set(previous_files)]

    # Work out the default. A default whose file is gone is removed, never
    # silently repointed at an unrelated file.
    if args.clear_default:
        default, note = None, "cleared on request"
    elif args.default:
        requested = args.default.strip().lstrip("./")
        if requested not in on_disk:
            print(f"error: {requested!r} is not one of the known files:", file=sys.stderr)
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
        print("warning: no .json files found under assets/ - the file list is now empty",
              file=sys.stderr)

    report(removed, added, default, note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
