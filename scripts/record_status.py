#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write status/YYYY-MM-DD.json (send result reported by the Windows publisher) and push.

Example:
  python3 scripts/record_status.py --date 2026-10-11 --status verified --verified \
      --target-mode filehelper --host caroline --ts 2026-10-11T09:01:12+11:00
Exit codes: 0 ok, 1 bad args, 4 git error.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import newslib as nl  # noqa: E402

STATUSES = ("pending", "sent", "verified", "failed", "skipped")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Sydney date (default today)")
    ap.add_argument("--edition-id", default=None)
    ap.add_argument("--status", required=True, choices=STATUSES)
    ap.add_argument("--target-mode", default="filehelper", choices=("filehelper", "group"))
    ap.add_argument("--verified", action="store_true")
    ap.add_argument("--error", default="")
    ap.add_argument("--host", default="")
    ap.add_argument("--ts", default=None, help="event time (default now, Sydney)")
    ap.add_argument("--repo", default=str(nl.REPO_ROOT))
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    date = a.date or nl.sydney_today()
    try:
        import datetime as dt
        dt.date.fromisoformat(date)
    except ValueError:
        print("bad --date", file=sys.stderr)
        return 1
    try:
        if not a.no_push:
            nl.sync_repo(repo)
    except RuntimeError as e:
        print(f"GIT ERROR: {e}", file=sys.stderr)
        return 4
    path = repo / "status" / f"{date}.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    event = {
        "edition_id": a.edition_id or date,
        "target_mode": a.target_mode,
        "status": a.status,
        "verified": bool(a.verified),
        "error": a.error,
        "host": a.host,
        "ts": a.ts or nl.sydney_now().isoformat(),
    }
    history = prev.get("history", [])
    history.append(event)
    doc = dict(event, date=date, recorded_at=nl.sydney_now().isoformat(), history=history[-20:])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(nl.dump_json(doc), encoding="utf-8", newline="\n")
    if a.no_push:
        print(f"WROTE {path.relative_to(repo)}")
        return 0
    try:
        sha = nl.commit_and_push([path], f"status: {date} {a.status}", repo=repo)
    except RuntimeError as e:
        print(f"GIT ERROR: {e}", file=sys.stderr)
        return 4
    print(f"RECORDED {path.relative_to(repo)} commit={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
