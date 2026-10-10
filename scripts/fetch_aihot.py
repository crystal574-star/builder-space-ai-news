#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dump AIHOT hot topics (and optional story details) to JSON for the daily routine.

Only https://aihot.news/api/v1 is used (aihot.virxact.com and /api/public/* retire 2026-10-31).
Story links in hot-topics may still point at the old domain; they are rewritten to
https://aihot.news/story/<publicId>, and the canonical link from /api/v1/stories is preferred.

Usage:
  python3 scripts/fetch_aihot.py                          # hot topics -> stdout
  python3 scripts/fetch_aihot.py -o /tmp/aihot.json --stories top   # + story details for all 10
  python3 scripts/fetch_aihot.py --stories 4e124b64-...,bb1411a1-...

AIHOT terms (https://aihot.news/terms): free for personal / public-interest non-commercial /
organization-internal use; keep attribution & canonical links; contact wzglyay@virxact.com
before any external commercial use or bulk public redistribution.
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://aihot.news/api/v1"
UA = "aihot-api/2.0.0"
_STORY_RE = re.compile(r"/story/([A-Za-z0-9-]+)/?$")


def get(path, retries=2):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries:
                time.sleep(min(int(e.headers.get("Retry-After") or 5), 60))
                continue
            if 500 <= e.code < 600 and attempt < retries:
                time.sleep(3)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries:
                time.sleep(3)
                continue
            raise


def story_id(topic):
    m = _STORY_RE.search((topic.get("links") or {}).get("story") or "")
    return m.group(1) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", help="write JSON here (default stdout)")
    ap.add_argument("--stories", default="", help="'top' for every hot topic, or comma-separated publicIds")
    a = ap.parse_args(argv)

    hot = get("/hot-topics")
    topics = []
    for t in hot.get("items", []):
        sid = story_id(t)
        links = dict(t.get("links") or {})
        topics.append({
            "rank": t.get("rank"), "id": t.get("id"), "title": t.get("title"),
            "lead_source": (t.get("source") or {}).get("name"),
            "original_url": links.get("original"), "aihot_item_url": links.get("aihot"),
            "story_public_id": sid,
            "aihot_story_url": f"https://aihot.news/story/{sid}" if sid else None,
            "source_count": t.get("sourceCount"), "signal_count": t.get("signalCount"),
            "participant_count": t.get("participantCount"), "source_names": t.get("sourceNames", []),
            "latest_at": t.get("latestAt"),
        })

    want = [x["story_public_id"] for x in topics if x["story_public_id"]] if a.stories == "top" else \
        [s.strip() for s in a.stories.split(",") if s.strip()]
    stories = {}
    for sid in want:
        try:
            st = get(f"/stories/{sid}")["story"]
        except Exception as e:
            stories[sid] = {"error": str(e)}
            continue
        stories[sid] = {
            "title": st.get("title"), "aihot_url": (st.get("links") or {}).get("aihot"),
            "status": st.get("status"), "source_count": st.get("sourceCount"),
            "report_count": st.get("reportCount"), "first_report_at": st.get("firstReportAt"),
            "latest_at": st.get("latestAt"), "latest": st.get("latest"), "digest": st.get("digest"),
            "reports": [{"title": r.get("title"), "summary": r.get("summary"),
                         "source": (r.get("source") or {}).get("name"),
                         "first_party": (r.get("source") or {}).get("firstParty"),
                         "published_at": r.get("publishedAt"),
                         "original_url": (r.get("links") or {}).get("original"),
                         "aihot_url": (r.get("links") or {}).get("aihot")} for r in st.get("reports", [])],
        }
        time.sleep(1)  # stay far below ~60 req/min
        for t in topics:
            if t["story_public_id"] == sid and stories[sid].get("aihot_url"):
                t["aihot_story_url"] = stories[sid]["aihot_url"]

    out = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "source": "AIHOT (https://aihot.news)",
           "terms": "https://aihot.news/terms", "hot_topics": topics, "stories": stories}
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {a.output}: {len(topics)} hot topics, {len(stories)} stories", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
