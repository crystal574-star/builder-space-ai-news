# -*- coding: utf-8 -*-
"""Shared helpers for the box-side scripts (stdlib only, Python 3.9+).

Validation mirrors schema/news.schema.json so no third-party dependency is needed.
The GitHub token is only read from the BUILDER_NEWS_GH_TOKEN environment variable
and handed to git through an inline credential helper; it never appears in argv,
files, or output.
"""
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

SYD = ZoneInfo("Australia/Sydney")
REPO_ROOT = Path(__file__).resolve().parent.parent
ORGS = ("OpenAI", "Anthropic", "Google DeepMind", "NVIDIA", "other")
HEADER_PREFIX = "Builder Space 每日 AI 速递 · "
FOOTER = "Builder Space Bot 自动整理，仅供参考，请以原文为准。\n来源：X 公开动态"
FOOTER_AIHOT = "Builder Space Bot 自动整理，仅供参考，请以原文为准。\n来源：X 公开动态、AIHOT（aihot.news）"
ORIGINS = ("x", "aihot", "x+aihot")
ORG_LABELS = {"other": "业界"}  # display label in message_text only
MAX_OTHER = 2
_AIHOT_URL = re.compile(r"^https://aihot\.news/(story|items)/[A-Za-z0-9-]+$")
TOKEN_ENV = "BUILDER_NEWS_GH_TOKEN"
REMOTE_URL = "https://github.com/crystal574-star/builder-space-ai-news.git"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EDITION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(-[a-z0-9]+)?$")
_GEN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+1[01]:00$")
_POSTED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
TOP_KEYS = {"date", "edition_id", "generated_at", "items", "message_text", "content_sha256"}
ITEM_KEYS = {"id", "org", "title_zh", "summary_zh", "source_url", "posted_at"}
OPTIONAL_ITEM_KEYS = {"origin", "aihot_url", "aihot_rank", "aihot_source_count", "aihot_signal_count",
                      "aihot_participant_count", "aihot_id"}
ITEM_ORDER = ("id", "org", "title_zh", "summary_zh", "source_url", "posted_at", "origin", "aihot_url",
              "aihot_rank", "aihot_source_count", "aihot_signal_count", "aihot_participant_count", "aihot_id")


def sydney_now() -> _dt.datetime:
    return _dt.datetime.now(SYD).replace(microsecond=0)


def sydney_today() -> str:
    return sydney_now().date().isoformat()


def url_id(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def header_for(date_str: str) -> str:
    d = _dt.date.fromisoformat(date_str)
    return f"{HEADER_PREFIX}{d.month}月{d.day}日"


def build_message_text(edition: dict) -> str:
    """Briefing layout: numbered title + summary, then a 【来源】 block, then the footer."""
    items = edition["items"]
    lines = [header_for(edition["date"]), ""]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. 【{ORG_LABELS.get(it['org'], it['org'])}】{it['title_zh']}")
        lines.append(it["summary_zh"])
        lines.append("")
    lines.append("——")
    lines.append("【来源】")
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] 原文 {it['source_url']}")
        if it.get("aihot_url"):
            rank = f"（热点榜第 {it['aihot_rank']}）" if it.get("aihot_rank") else ""
            lines.append(f"    AIHOT {it['aihot_url']}{rank}")
    lines.append("")
    uses_aihot = any(it.get("aihot_url") for it in items)
    lines.append(FOOTER_AIHOT if uses_aihot else FOOTER)
    return "\n".join(lines)


def build_edition(draft: dict) -> dict:
    """Fill derived fields (ids, generated_at, edition_id, message_text, sha)."""
    ed = dict(draft)
    ed.setdefault("date", sydney_today())
    ed.setdefault("edition_id", ed["date"])
    ed.setdefault("generated_at", sydney_now().isoformat())
    items = []
    for it in ed.get("items", []):
        it = dict(it)
        it["id"] = url_id(it["source_url"])
        if "origin" not in it:
            it["origin"] = "x+aihot" if it.get("aihot_url") and "x.com/" in it["source_url"] else (
                "aihot" if it.get("aihot_url") else "x")
        items.append({k: it[k] for k in ITEM_ORDER if k in it})
    ed["items"] = items
    ed["message_text"] = build_message_text(ed)
    ed["content_sha256"] = sha256_text(ed["message_text"])
    return {k: ed[k] for k in ("date", "edition_id", "generated_at", "items", "message_text", "content_sha256")}


def validate_edition(ed, expected_date=None) -> list:
    """Return a list of error strings (empty list == valid)."""
    errs = []
    if not isinstance(ed, dict):
        return ["edition must be a JSON object"]
    missing = TOP_KEYS - ed.keys()
    extra = ed.keys() - TOP_KEYS
    if missing:
        errs.append(f"missing keys: {sorted(missing)}")
    if extra:
        errs.append(f"unexpected keys: {sorted(extra)}")
    if missing:
        return errs
    if not isinstance(ed["date"], str) or not _DATE_RE.match(ed["date"]):
        errs.append("date must be YYYY-MM-DD")
    else:
        try:
            _dt.date.fromisoformat(ed["date"])
        except ValueError:
            errs.append("date is not a real calendar date")
    if expected_date and ed["date"] != expected_date:
        errs.append(f"date {ed['date']} != expected {expected_date}")
    if not isinstance(ed["edition_id"], str) or not _EDITION_RE.match(ed["edition_id"]):
        errs.append("edition_id must look like YYYY-MM-DD")
    elif not ed["edition_id"].startswith(str(ed["date"])):
        errs.append("edition_id must start with date")
    if not isinstance(ed["generated_at"], str) or not _GEN_RE.match(ed["generated_at"]):
        errs.append("generated_at must be ISO 8601 with +11:00/+10:00 offset")
    items = ed["items"]
    if not isinstance(items, list) or len(items) != 5:
        errs.append("items must be a list of exactly 5")
        items = items if isinstance(items, list) else []
    seen = set()
    for n, it in enumerate(items, 1):
        p = f"items[{n}]"
        if not isinstance(it, dict):
            errs.append(f"{p} must be an object")
            continue
        if ITEM_KEYS - it.keys():
            errs.append(f"{p} missing keys: {sorted(ITEM_KEYS - it.keys())}")
            continue
        if it.keys() - ITEM_KEYS - OPTIONAL_ITEM_KEYS:
            errs.append(f"{p} unexpected keys: {sorted(it.keys() - ITEM_KEYS - OPTIONAL_ITEM_KEYS)}")
        if "origin" in it and it["origin"] not in ORIGINS:
            errs.append(f"{p}.origin must be one of {ORIGINS}")
        if "aihot_url" in it and not (isinstance(it["aihot_url"], str) and _AIHOT_URL.match(it["aihot_url"])):
            errs.append(f"{p}.aihot_url must be https://aihot.news/story/<id> or /items/<id> (not the retired domain)")
        if it.get("origin") in ("aihot", "x+aihot") and "aihot_url" not in it:
            errs.append(f"{p}.origin={it['origin']} requires aihot_url")
        if "aihot_rank" in it and not (isinstance(it["aihot_rank"], int) and 1 <= it["aihot_rank"] <= 10):
            errs.append(f"{p}.aihot_rank must be an integer 1..10")
        for k in ("aihot_source_count", "aihot_signal_count", "aihot_participant_count"):
            if k in it and not (isinstance(it[k], int) and it[k] >= 0):
                errs.append(f"{p}.{k} must be a non-negative integer")
        if it["org"] not in ORGS:
            errs.append(f"{p}.org invalid: {it['org']!r}")
        for k, mx in (("title_zh", 60), ("summary_zh", 120)):
            v = it[k]
            if not isinstance(v, str) or not v.strip():
                errs.append(f"{p}.{k} must be a non-empty string")
            elif len(v) > mx:
                errs.append(f"{p}.{k} too long ({len(v)} > {mx} chars)")
        url = it["source_url"]
        if not isinstance(url, str) or not url.startswith("https://"):
            errs.append(f"{p}.source_url must be https://")
        else:
            if it["id"] != url_id(url):
                errs.append(f"{p}.id does not match sha256(source_url)[:16]")
            if url in seen:
                errs.append(f"{p}.source_url duplicated")
            seen.add(url)
        if not isinstance(it["id"], str) or not _HEX16.match(it["id"]):
            errs.append(f"{p}.id must be 16 hex chars")
        if not isinstance(it["posted_at"], str) or not _POSTED_RE.match(it["posted_at"]):
            errs.append(f"{p}.posted_at must be ISO 8601 with zone")
    if sum(1 for it in items if isinstance(it, dict) and it.get("org") == "other") > MAX_OTHER:
        errs.append(f"at most {MAX_OTHER} items may have org 'other'")
    mt = ed["message_text"]
    if not isinstance(mt, str) or not (20 <= len(mt) <= 4000):
        errs.append("message_text must be a string of 20..4000 chars")
    else:
        if isinstance(ed["date"], str) and _DATE_RE.match(ed["date"]):
            if mt.splitlines()[0] != header_for(ed["date"]):
                errs.append("message_text first line must be the header for date")
        for it in items:
            if isinstance(it, dict) and isinstance(it.get("source_url"), str) and it["source_url"] not in mt:
                errs.append(f"message_text missing link {it['source_url']}")
            if isinstance(it, dict) and isinstance(it.get("aihot_url"), str) and it["aihot_url"] not in mt:
                errs.append(f"message_text missing AIHOT link {it['aihot_url']}")
        if any(isinstance(it, dict) and it.get("aihot_url") for it in items) and "AIHOT（aihot.news）" not in mt:
            errs.append("message_text must credit AIHOT（aihot.news） when AIHOT items are included")
        if not isinstance(ed["content_sha256"], str) or not _HEX64.match(ed["content_sha256"]):
            errs.append("content_sha256 must be 64 hex chars")
        elif ed["content_sha256"] != sha256_text(mt):
            errs.append("content_sha256 does not match message_text")
    return errs


def dump_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------- git helpers
_CRED_HELPER = (
    "!f() { test \"$1\" = get || exit 0; echo username=x-access-token; "
    "echo \"password=${%s}\"; }; f" % TOKEN_ENV
)


def git(*args, repo=REPO_ROOT, auth=False, check=True) -> subprocess.CompletedProcess:
    cmd = ["git"]
    if auth:
        cmd += ["-c", "credential.helper=", "-c", f"credential.helper={_CRED_HELPER}"]
    cmd += list(args)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    res = subprocess.run(cmd, cwd=str(repo), env=env, capture_output=True, text=True)
    tok = os.environ.get(TOKEN_ENV)
    if tok:  # defensive scrub, git should never echo it
        res = subprocess.CompletedProcess(res.args, res.returncode,
                                          res.stdout.replace(tok, "***"), res.stderr.replace(tok, "***"))
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {res.stderr.strip()}")
    return res


def sync_repo(repo=REPO_ROOT) -> None:
    """Fast-forward local main to origin/main (no-op on an empty remote)."""
    if not os.environ.get(TOKEN_ENV):
        raise RuntimeError(f"{TOKEN_ENV} is not set")
    git("fetch", "origin", repo=repo, auth=True)
    if git("rev-parse", "--verify", "-q", "origin/main", repo=repo, check=False).returncode == 0:
        git("merge", "--ff-only", "origin/main", repo=repo)


def commit_and_push(paths, message, repo=REPO_ROOT) -> str:
    git("add", "--", *[str(p) for p in paths], repo=repo)
    if git("diff", "--cached", "--quiet", repo=repo, check=False).returncode == 0:
        return git("rev-parse", "HEAD", repo=repo).stdout.strip()
    git("-c", "user.name=Builder Space Bot", "-c", "user.email=builder-space-bot@users.noreply.github.com",
        "commit", "-q", "-m", message, repo=repo)
    git("push", "-q", "origin", "HEAD:main", repo=repo, auth=True)
    return git("rev-parse", "HEAD", repo=repo).stdout.strip()


def status_is_sent(date_str: str, repo=REPO_ROOT) -> bool:
    p = Path(repo) / "status" / f"{date_str}.json"
    if not p.exists():
        return False
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return True  # unreadable status: be conservative
    return st.get("status") in ("sent", "verified") or bool(st.get("verified"))
