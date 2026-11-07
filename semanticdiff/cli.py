"""``semantic-diff`` command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional

from .core import classify, clauses, diff, extract_formats

__version__ = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="semantic-diff",
        description="Diff two prompt versions by behaviour, not by characters.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    compare = sub.add_parser("diff", help="classify the change between two prompts")
    compare.add_argument("before")
    compare.add_argument("after")
    compare.add_argument("--similarity", type=float, default=0.6,
                         help="clauses above this ratio are 'changed', not add+remove")
    compare.add_argument("--json", action="store_true")
    compare.add_argument("--fail-on-breaking", action="store_true",
                         help="exit 1 when a breaking change is found")
    compare.add_argument("--fail-on-change", action="store_true",
                         help="exit 1 on any behavioural change")

    inspect = sub.add_parser("classify", help="show each clause and its category")
    inspect.add_argument("file")
    inspect.add_argument("--json", action="store_true")
    return parser


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit("cannot read %s: %s" % (path, exc))


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "classify":
        text = _read(args.file)
        rows = [{"clause": clause, "category": classify(clause)}
                for clause in clauses(text)]
        if args.json:
            print(json.dumps({"formats": sorted(extract_formats(text)), "clauses": rows},
                             indent=2))
        else:
            print("%s: %d clause(s)" % (args.file, len(rows)))
            for row in rows:
                print("  [%-10s] %s" % (row["category"], row["clause"]))
            formats = sorted(extract_formats(text))
            if formats:
                print("formats: %s" % ", ".join(formats))
        return 0

    before = _read(args.before)
    after = _read(args.after)
    result = diff(before, after, similarity=args.similarity)

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    elif not result:
        print("no behavioural change")
    else:
        print(result.summary())
        for label, changes in (("added", result.added), ("removed", result.removed),
                               ("changed", result.changed)):
            for change in changes:
                if change.action == "changed":
                    print("  [%-7s %-10s] %r -> %r"
                          % (change.severity, change.category,
                             change.before, change.after))
                elif change.action == "removed":
                    print("  [%-7s %-10s] %r" % (change.severity, change.category,
                                                 change.before))
                else:
                    print("  [%-7s %-10s] %r" % (change.severity, change.category,
                                                 change.after))

    if args.fail_on_breaking and result.breaking:
        return 1
    if args.fail_on_change and result:
        return 1
    return 0
