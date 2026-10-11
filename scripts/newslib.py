# -*- coding: utf-8 -*-
"""Shared helpers for the box-side scripts (stdlib only, Python 3.9+).

Validation mirrors schema/news.schema.json so no third-party dependency is needed.
The GitHub token is only read from the BUILDER_NEWS_GH_TOKEN environment variable
and handed to git through an inline credential helper; it never appears in argv,
files, or output.

Edition model
-------------
edition_id  = YYYY-MM-DD (default/morning) or YYYY-MM-DD-<label> (e.g. 2026-10-11-noon)
file        = news/<edition_id>.json, status/<edition_id>.json
header      = first line, e.g. 'Builder Space 每日 AI 速递 · 午间版 · 10月11日'
tag         = LAST line, e.g. '#BS-1011' / '#BS-1011-noon' (used by the Windows publisher to verify)
tone        = 'normal' | 'cute' (playful + emoji, one quip per item; v2 approved 2026-10-11, NOT the old 嗲 style)
Editions published before the tag existed (news/2026-10-11.json) are "legacy": no tag/tone keys.
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
TONES = ("normal", "cute")
HEADER_PREFIX = "Builder Space 每日 AI 速递 · "
DISCLAIMER = "Builder Space Bot 自动整理，仅供参考，请以原文为准。"
CREDIT_X = "来源：X 公开动态"
CREDIT_AIHOT = "来源：X 公开动态、AIHOT（aihot.news）"
FOOTER = f"{DISCLAIMER}\n{CREDIT_X}"
FOOTER_AIHOT = f"{DISCLAIMER}\n{CREDIT_AIHOT}"
EDITION_LABELS = {"noon": "午间版", "evening": "晚间版", "extra": "特别版"}
# Cute tone v2 (approved 2026-10-11 16:22): playful, lots of emoji, one quip per item, not 嗲.
CUTE_SALUTATION = {"": "早安", "noon": "午安", "evening": "晚上好"}  # other labels: '哈喽大家好呀'
CUTE_GREETING = "哈喽大家{salutation}呀 👋🌸 新鲜的 AI 速递送到啦～今天挑了 5 条值得一看的，冲！🚀"
CUTE_CLOSING = "今天就到这里啦～明天见 👋 有想聊的随时找我 😊💬"
CUTE_BANNED = ("人家", "宝宝", "摸摸头", "爱你们", "嗲")  # the old soft-cute style, must not come back
MAX_ASIDES = 5
ASIDE_MAX_LEN = 40
ASIDE_MAX_EMOJI = 3
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\u3030\u303D\u3297\u3299]")
_EMOJI_JOINERS = re.compile("[\uFE0F\u200D\U0001F3FB-\U0001F3FF]")
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
OPTIONAL_TOP_KEYS = {"tone", "tag"}
TOP_ORDER = ("date", "edition_id", "tone", "tag", "generated_at", "items", "message_text", "content_sha256")
ITEM_KEYS = {"id", "org", "title_zh", "summary_zh", "source_url", "posted_at"}
OPTIONAL_ITEM_KEYS = {"title_emoji", "aside_zh", "origin", "aihot_url", "aihot_rank", "aihot_source_count", "aihot_signal_count",
                      "aihot_participant_count", "aihot_id"}
ITEM_ORDER = ("id", "org", "title_zh", "title_emoji", "summary_zh", "aside_zh", "source_url", "posted_at", "origin", "aihot_url",
              "aihot_rank", "aihot_source_count", "aihot_signal_count", "aihot_participant_count", "aihot_id")


def sydney_now() -> _dt.datetime:
    return _dt.datetime.now(SYD).replace(microsecond=0)


def sydney_today() -> str:
    return sydney_now().date().isoformat()


def url_id(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def edition_label(date_str: str, edition_id: str = "") -> str:
    """'' for the default edition, else the suffix ('noon')."""
    e = edition_id or ""
    return e[len(date_str) + 1:] if e.startswith(date_str + "-") else ""


def header_for(date_str: str, edition_id: str = "") -> str:
    """Morning: '… · 10月11日'; labelled: '… · 午间版 · 10月11日' (label before the date, so no header
    is a substring of another)."""
    d = _dt.date.fromisoformat(date_str)
    suffix = edition_label(date_str, edition_id)
    label = EDITION_LABELS.get(suffix, suffix)
    return f"{HEADER_PREFIX}{label + ' · ' if label else ''}{d.month}月{d.day}日"


def tag_for(date_str: str, edition_id: str = "") -> str:
    d = _dt.date.fromisoformat(date_str)
    suffix = edition_label(date_str, edition_id)
    return f"#BS-{d.month:02d}{d.day:02d}{'-' + suffix if suffix else ''}"


def edition_relpath(edition_id: str, kind: str = "news") -> str:
    return f"{kind}/{edition_id}.json"


def _sources_block(items) -> list:
    lines = ["——", "【来源】"]
    for i, it in enumerate(items, 1):
        lines.append(f"[{i}] 原文 {it['source_url']}")
        if it.get("aihot_url"):
            rank = f"（热点榜第 {it['aihot_rank']}）" if it.get("aihot_rank") else ""
            lines.append(f"    AIHOT {it['aihot_url']}{rank}")
    return lines


def build_message_text(edition: dict) -> str:
    """Briefing layout. normal: header, items, sources, footer, tag.
    cute: header, greeting line, items (title + emoji, summary, quip), closing, sources, footer, tag."""
    items = edition["items"]
    date, eid = edition["date"], edition.get("edition_id", "")
    tone = edition.get("tone", "normal")
    suffix = edition_label(date, eid)
    lines = [header_for(date, eid)]
    if tone == "cute":
        sal = CUTE_SALUTATION.get(suffix)
        lines.append(CUTE_GREETING.format(salutation=sal) if sal else CUTE_GREETING.replace("{salutation}", "好"))
    lines.append("")
    for i, it in enumerate(items, 1):
        emoji = f" {it['title_emoji']}" if tone == "cute" and it.get("title_emoji") else ""
        lines.append(f"{i}. 【{ORG_LABELS.get(it['org'], it['org'])}】{it['title_zh']}{emoji}")
        lines.append(it["summary_zh"])
        if tone == "cute" and it.get("aside_zh"):
            lines.append(f"（{it['aside_zh']}）")
        lines.append("")
    if tone == "cute":
        lines.append(CUTE_CLOSING)
        lines.append("")
    lines += _sources_block(items)
    lines.append("")
    uses_aihot = any(it.get("aihot_url") for it in items)
    lines.append(FOOTER_AIHOT if uses_aihot else FOOTER)
    lines.append(tag_for(date, eid))
    return "\n".join(lines)


def build_edition(draft: dict) -> dict:
    """Fill derived fields (ids, origin, generated_at, edition_id, tone, tag, message_text, sha)."""
    ed = dict(draft)
    ed.setdefault("date", sydney_today())
    ed.setdefault("edition_id", ed["date"])
    ed.setdefault("tone", "normal")
    ed.setdefault("generated_at", sydney_now().isoformat())
    ed["tag"] = tag_for(ed["date"], ed["edition_id"])
    items = []
    for it in ed.get("items", []):
        it = dict(it)
        it["id"] = url_id(it["source_url"])
        if "origin" not in it:
            it["origin"] = "x+aihot" if it.get("aihot_url") and "x.com/" in it["source_url"] else (
                "aihot" if it.get("aihot_url") else "x")
        for k in ("aside_zh", "title_emoji"):
            if not it.get(k):
                it.pop(k, None)
        items.append({k: it[k] for k in ITEM_ORDER if k in it})
    ed["items"] = items
    ed["message_text"] = build_message_text(ed)
    ed["content_sha256"] = sha256_text(ed["message_text"])
    return {k: ed[k] for k in TOP_ORDER if k in ed}


def emoji_count(text: str) -> int:
    return len(_EMOJI.findall(text))


def is_legacy(ed: dict) -> bool:
    return "tag" not in ed


def validate_edition(ed, expected_date=None, require_tag=False) -> list:
    """Return a list of error strings (empty list == valid). Legacy (untagged) editions are accepted
    unless require_tag is set."""
    errs = []
    if not isinstance(ed, dict):
        return ["edition must be a JSON object"]
    missing = TOP_KEYS - ed.keys()
    extra = ed.keys() - TOP_KEYS - OPTIONAL_TOP_KEYS
    if missing:
        errs.append(f"missing keys: {sorted(missing)}")
    if extra:
        errs.append(f"unexpected keys: {sorted(extra)}")
    if missing:
        return errs
    date_ok = isinstance(ed["date"], str) and bool(_DATE_RE.match(ed["date"]))
    if date_ok:
        try:
            _dt.date.fromisoformat(ed["date"])
        except ValueError:
            date_ok = False
    if not date_ok:
        errs.append("date must be a real YYYY-MM-DD date")
    if expected_date and ed["date"] != expected_date:
        errs.append(f"date {ed['date']} != expected {expected_date}")
    eid_ok = isinstance(ed["edition_id"], str) and bool(_EDITION_RE.match(ed["edition_id"])) \
        and ed["edition_id"].startswith(str(ed["date"]))
    if not eid_ok:
        errs.append("edition_id must be YYYY-MM-DD or YYYY-MM-DD-<label>, starting with date")
    if not isinstance(ed["generated_at"], str) or not _GEN_RE.match(ed["generated_at"]):
        errs.append("generated_at must be ISO 8601 with +11:00/+10:00 offset")
    tone = ed.get("tone", "normal")
    if tone not in TONES:
        errs.append(f"tone must be one of {TONES}")
    if require_tag and is_legacy(ed):
        errs.append("tag missing (legacy edition): rebuild with --build")
    items = ed["items"]
    if not isinstance(items, list) or len(items) != 5:
        errs.append("items must be a list of exactly 5")
        items = items if isinstance(items, list) else []
    seen = set()
    asides = 0
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
        if "aside_zh" in it:
            a = it["aside_zh"]
            asides += 1
            if not isinstance(a, str) or not a.strip() or len(a) > ASIDE_MAX_LEN:
                errs.append(f"{p}.aside_zh must be 1..{ASIDE_MAX_LEN} chars")
            elif re.search(r"\d|https?://|[（）()]", a):
                errs.append(f"{p}.aside_zh must be playful only: no digits, links or brackets (facts stay in summary_zh)")
            elif tone == "cute" and not (1 <= emoji_count(a) <= ASIDE_MAX_EMOJI):
                errs.append(f"{p}.aside_zh needs 1..{ASIDE_MAX_EMOJI} emoji")
        elif tone == "cute":
            errs.append(f"{p}.aside_zh required in cute tone (one quip per item)")
        if "title_emoji" in it:
            te = it["title_emoji"]
            if not isinstance(te, str) or not (1 <= emoji_count(te) <= 2) or _EMOJI_JOINERS.sub("", _EMOJI.sub("", te)).strip():
                errs.append(f"{p}.title_emoji must be 1-2 emoji and nothing else")
        elif tone == "cute":
            errs.append(f"{p}.title_emoji required in cute tone")
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
    if asides > MAX_ASIDES:
        errs.append(f"at most {MAX_ASIDES} items may have aside_zh")
    if sum(1 for it in items if isinstance(it, dict) and it.get("org") == "other") > MAX_OTHER:
        errs.append(f"at most {MAX_OTHER} items may have org 'other'")
    mt = ed["message_text"]
    if tone == "cute" and isinstance(mt, str):
        hit = [w for w in CUTE_BANNED if w in mt]
        if hit:
            errs.append(f"cute tone must not use the old 嗲 wording: {hit}")
    if not isinstance(mt, str) or not (20 <= len(mt) <= 4000):
        errs.append("message_text must be a string of 20..4000 chars")
        return errs
    lines = mt.splitlines()
    if date_ok and eid_ok:
        if lines[0] != header_for(ed["date"], ed["edition_id"]):
            errs.append("message_text first line must be the header for date/edition")
        if not is_legacy(ed):
            want = tag_for(ed["date"], ed["edition_id"])
            if ed["tag"] != want:
                errs.append(f"tag must be {want}")
            if lines[-1] != want:
                errs.append(f"message_text last line must be the tag {want}")
    for it in items:
        if not isinstance(it, dict):
            continue
        for k in ("source_url", "aihot_url"):
            if isinstance(it.get(k), str) and it[k] not in mt:
                errs.append(f"message_text missing {'AIHOT ' if k == 'aihot_url' else ''}link {it[k]}")
        if not is_legacy(ed):
            for k in ("title_zh", "summary_zh"):
                if isinstance(it.get(k), str) and it[k] not in mt:
                    errs.append(f"message_text missing {k} of {it.get('source_url')}")
            if tone == "cute" and isinstance(it.get("aside_zh"), str) and f"（{it['aside_zh']}）" not in mt:
                errs.append(f"message_text missing aside of {it.get('source_url')}")
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


SENT_STATUSES = ("sent", "verified", "unverified")  # unverified = keystrokes were sent, delivery not confirmed


def status_is_sent(edition_id: str, repo=REPO_ROOT) -> bool:
    p = Path(repo) / edition_relpath(edition_id, "status")
    if not p.exists():
        return False
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return True  # unreadable status: be conservative
    return st.get("status") in SENT_STATUSES or bool(st.get("verified"))
