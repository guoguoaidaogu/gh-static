#!/usr/bin/env python3
"""Put the keys of a JSON file, and the strings inside its arrays, in order.

Usage:
    python3 scripts/sort_json.py assets/ExampleChapter/Example.json
    python3 scripts/sort_json.py i18n/*.json --indent 2
    python3 scripts/sort_json.py i18n/zh-Hans.json --check
    python3 scripts/sort_json.py i18n/en.json --stdout
    python3 scripts/sort_json.py i18n/en.json --shallow
    python3 scripts/sort_json.py assets/Fudan/*.json --keep-array-order

Keys are compared with Python's default string ordering (Unicode code points),
so the result is stable across runs and platforms and matches what a plain
sort in the editor produces. Nested objects are sorted too unless --shallow is
given, and objects inside arrays are sorted as well.

Arrays are sorted when every element is a string; a mixed array has no
meaningful string order, so it is left alone and only its elements are sorted
internally. Note that an array of strings can carry meaning in its order — the
choice lists in assets/Fudan/*.json are multiple-choice options — so
--keep-array-order limits the script to object keys and leaves every array in
the order it was written.

The file is rewritten in place, with its original indentation and trailing
newline preserved unless --indent or --no-newline say otherwise, so sorting a
file only reorders keys and array elements and never restyles it.

--check does not write anything: it reports the files that are out of order and
exits non-zero, so it can be wired into CI. --stdout prints the sorted JSON
instead of touching the file. The script is safe to re-run: sorted input is
rewritten unchanged (and reported as already sorted).
"""

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def detect_indent(text: str, default: int = 2) -> int:
    """Indentation of the first indented line, so a rewrite keeps the style.

    The opening brace of an object or array is not indented, so only lines that
    actually start with whitespace are measured.
    """
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped and stripped != line:
            return len(line) - len(stripped)
    return default


def sort_keys(value, recursive: bool = True, arrays: bool = True):
    """Return value with objects and string arrays in dictionary order.

    Objects are rebuilt with sorted keys. An array whose elements are all
    strings is sorted; any other array keeps its element order and is only
    recursed into, since a mixed array has no meaningful string order. Scalars
    pass through. With recursive=False nothing below the top level is touched.
    """
    if isinstance(value, dict):
        if not recursive:
            return {key: value[key] for key in sorted(value)}
        return {key: sort_keys(value[key], recursive, arrays) for key in sorted(value)}
    if isinstance(value, list):
        if not recursive:
            return value
        items = [sort_keys(item, recursive, arrays) for item in value]
        if arrays and all(isinstance(item, str) for item in items):
            return sorted(items)
        return items
    return value


def is_sorted(value, recursive: bool = True, arrays: bool = True) -> bool:
    """True when every object, and every string array, is already in order."""
    if isinstance(value, dict):
        keys = list(value)
        if keys != sorted(keys):
            return False
        if recursive:
            return all(is_sorted(value[key], recursive, arrays) for key in keys)
    elif isinstance(value, list):
        if not recursive:
            return True
        if arrays and all(isinstance(item, str) for item in value) and value != sorted(value):
            return False
        return all(is_sorted(item, recursive, arrays) for item in value)
    return True


def load(path: pathlib.Path) -> tuple[object, str]:
    """Parse a JSON document, returning (data, raw text)."""
    text = path.read_text(encoding="utf-8")
    return json.loads(text), text


def render(data: object, indent: int) -> str:
    return json.dumps(data, indent=indent, ensure_ascii=False)


def process(path: pathlib.Path, args) -> int:
    """Handle one file. Returns 0 on success, 1 on failure, 2 when --check fails."""
    try:
        data, text = load(path)
    except OSError as err:
        print(f"error: cannot read {path}: {err}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as err:
        print(f"error: {path} is not valid JSON: {err}", file=sys.stderr)
        return 1

    indent = args.indent if args.indent is not None else detect_indent(text)
    newline = "" if args.no_newline else "\n"

    if args.check:
        if is_sorted(data, not args.shallow, not args.keep_array_order):
            print(f"{path}: in order")
            return 0
        print(f"{path}: keys and/or string arrays are not in dictionary order",
              file=sys.stderr)
        return 2

    sorted_data = sort_keys(data, not args.shallow, not args.keep_array_order)
    output = render(sorted_data, indent) + newline

    if args.stdout:
        sys.stdout.write(output)
        return 0

    if output == text:
        print(f"{path}: already sorted ({len(data)} keys)" if isinstance(data, dict)
              else f"{path}: already sorted")
        return 0

    try:
        path.write_text(output, encoding="utf-8")
    except OSError as err:
        print(f"error: cannot write {path}: {err}", file=sys.stderr)
        return 1

    count = f" ({len(data)} keys)" if isinstance(data, dict) else ""
    print(f"{path}: sorted{count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=("Sort the keys of a JSON file, and the strings inside its "
                     "arrays, into dictionary order."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("files", metavar="FILE", nargs="+", type=pathlib.Path,
                        help="JSON file to sort (rewritten in place)")
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit non-zero when a file is unsorted")
    parser.add_argument("--stdout", action="store_true",
                        help="print the sorted JSON instead of writing the file")
    parser.add_argument("--shallow", action="store_true",
                        help="sort only the top level, leaving nested objects and arrays alone")
    parser.add_argument("--keep-array-order", action="store_true",
                        help="sort object keys only; leave every array as written")
    parser.add_argument("--indent", type=int, metavar="N",
                        help="indentation width (default: keep the file's own)")
    parser.add_argument("--no-newline", action="store_true",
                        help="do not end the written file with a newline")
    args = parser.parse_args()

    if args.indent is not None and args.indent < 0:
        print("error: --indent must not be negative", file=sys.stderr)
        return 1
    if args.check and args.stdout:
        print("error: --check and --stdout cannot be combined", file=sys.stderr)
        return 1

    status = 0
    for path in args.files:
        if not path.is_file():
            print(f"error: {path} does not exist", file=sys.stderr)
            status = max(status, 1)
            continue
        status = max(status, process(path, args))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
