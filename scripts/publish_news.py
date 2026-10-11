#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate a news edition and publish it to news/<edition_id>.json.

news/YYYY-MM-DD.json is the default (morning) edition; labelled editions such as
edition_id 2026-10-11-noon go to news/2026-10-11-noon.json, so nothing overwrites the morning file.
New editions must carry the tag line (built by --build); legacy untagged files are only re-checked.

Usage:
  python3 scripts/publish_news.py edition.json            # validate, write, commit, push
  python3 scripts/publish_news.py draft.json --build      # fill id/message_text/sha first
  python3 scripts/publish_news.py edition.json --no-push  # local only
  python3 scripts/publish_news.py edition.json --dry-run  # validate + print, touch nothing
  python3 scripts/publish_news.py draft.json --build --preview-dir DIR --preview-suffix aihot  # preview files only

Exit codes: 0 published or no-op, 1 validation error, 3 refused (edition already sent), 4 git error.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import newslib as nl  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="edition JSON file, or - for stdin")
    ap.add_argument("--build", action="store_true", help="compute ids, message_text, content_sha256")
    ap.add_argument("--date", help="expected Sydney date (default: today in Australia/Sydney)")
    ap.add_argument("--repo", default=str(nl.REPO_ROOT))
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--preview-dir", help="validate and write <date>-<suffix>.json/.txt here; no repo/git changes")
    ap.add_argument("--preview-suffix", default="preview")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    repo = Path(a.repo)

    raw = sys.stdin.read() if a.input == "-" else Path(a.input).read_text(encoding="utf-8")
    ed = json.loads(raw)
    if a.build:
        ed = nl.build_edition(ed)
    expected = a.date or nl.sydney_today()
    errs = nl.validate_edition(ed, expected_date=expected)
    if errs:
        print("INVALID:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 1
    content = nl.dump_json(ed)
    if a.preview_dir:
        out = Path(a.preview_dir)
        out.mkdir(parents=True, exist_ok=True)
        base = out / f"{ed['edition_id']}-{a.preview_suffix}"
        base.with_suffix(".json").write_text(content, encoding="utf-8", newline="\n")
        base.with_suffix(".txt").write_text(ed["message_text"] + "\n", encoding="utf-8", newline="\n")
        print(f"PREVIEW {base}.json / .txt ({len(ed['message_text'])} chars) sha={ed['content_sha256'][:12]}")
        return 0
    if a.dry_run:
        print(ed["message_text"])
        print(f"\n[dry-run] valid edition {ed['edition_id']} sha={ed['content_sha256'][:12]}")
        return 0

    try:
        if not a.no_push:
            nl.sync_repo(repo)
    except RuntimeError as e:
        print(f"GIT ERROR: {e}", file=sys.stderr)
        return 4

    target = repo / nl.edition_relpath(ed["edition_id"])
    if target.exists():
        existing_text = target.read_text(encoding="utf-8")
        try:
            existing = json.loads(existing_text)
        except ValueError:
            existing = {}
        same = existing_text == content or (
            existing.get("content_sha256") == ed["content_sha256"] and existing.get("items") == ed["items"]
            and existing.get("edition_id") == ed["edition_id"])  # ignore a different generated_at
        if same:
            print(f"NO-OP: {target.relative_to(repo)} already has identical content")
            return 0
        if nl.status_is_sent(ed["edition_id"], repo):
            print(f"REFUSED: {ed['edition_id']} is already marked sent in status/; not overwriting", file=sys.stderr)
            return 3
    if nl.is_legacy(ed):
        print("INVALID: edition has no tag line (legacy format); rebuild it with --build", file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    if a.no_push:
        print(f"WROTE {target.relative_to(repo)} (not committed)")
        return 0
    try:
        sha = nl.commit_and_push([target], f"news: {ed['edition_id']}", repo=repo)
    except RuntimeError as e:
        print(f"GIT ERROR: {e}", file=sys.stderr)
        return 4
    print(f"PUBLISHED {target.relative_to(repo)} commit={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
