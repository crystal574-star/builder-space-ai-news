# -*- coding: utf-8 -*-
"""Offline tests for scripts/ (stdlib only). Run: python3 -m unittest discover -s tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import newslib as nl  # noqa: E402


def draft(eid="2026-10-11", tone="normal", asides=None):
    items = []
    for i, org in enumerate(["OpenAI", "Anthropic", "Google DeepMind", "NVIDIA", "other"]):
        it = {"org": org, "title_zh": f"标题{i}", "summary_zh": f"摘要内容{i}", "source_url": f"https://x.com/a/status/{i}",
              "posted_at": "2026-10-10T01:00:00Z"}
        if i == 1:
            it.update(aihot_url="https://aihot.news/story/abc-1", aihot_rank=2)
        if asides and i in asides:
            it["aside_zh"] = asides[i]
        items.append(it)
    return {"date": "2026-10-11", "edition_id": eid, "tone": tone, "generated_at": "2026-10-11T08:40:00+11:00",
            "items": items}


class TestBuild(unittest.TestCase):
    def test_normal_tag_last_line_header_first(self):
        ed = nl.build_edition(draft())
        lines = ed["message_text"].splitlines()
        self.assertEqual(lines[0], "Builder Space 每日 AI 速递 · 10月11日")
        self.assertEqual(lines[-1], "#BS-1011")
        self.assertEqual(ed["tag"], "#BS-1011")
        self.assertEqual(nl.validate_edition(ed, "2026-10-11", require_tag=True), [])
        self.assertNotIn("宝宝", ed["message_text"])

    def test_labelled_tag(self):
        ed = nl.build_edition(draft("2026-10-11-noon"))
        self.assertEqual(ed["message_text"].splitlines()[-1], "#BS-1011-noon")
        self.assertEqual(ed["message_text"].splitlines()[0], "Builder Space 每日 AI 速递 · 午间版 · 10月11日")
        self.assertEqual(nl.edition_relpath(ed["edition_id"]), "news/2026-10-11-noon.json")
        self.assertEqual(nl.edition_relpath("2026-10-11", "status"), "status/2026-10-11.json")

    def test_cute_layout(self):
        ed = nl.build_edition(draft("2026-10-11-noon", "cute", {0: "好耶~ 🌸", 3: "冲鸭~"}))
        lines = ed["message_text"].splitlines()
        self.assertEqual(lines[0], "Builder Space 每日 AI 速递 · 午间版 · 10月11日")
        self.assertEqual(lines[1], "哈喽哈喽~ Builder Space 的宝宝们午安呀 🌸✨")
        self.assertIn("（10月11日 午间版）", lines[2])
        i = lines.index("摘要内容0")
        self.assertEqual(lines[i + 1], "（好耶~ 🌸）")
        self.assertLess(lines.index(nl.CUTE_CLOSING), lines.index("【来源】"))
        self.assertEqual(lines[-1], "#BS-1011-noon")
        self.assertEqual(nl.validate_edition(ed, "2026-10-11"), [])

    def test_cute_morning_salutation(self):
        ed = nl.build_edition(draft("2026-10-11", "cute"))
        self.assertIn("宝宝们早安呀", ed["message_text"])
        self.assertIn("（10月11日）", ed["message_text"])

    def test_normal_ignores_asides(self):
        ed = nl.build_edition(draft(asides={0: "好耶~"}))
        self.assertNotIn("（好耶~）", ed["message_text"])
        self.assertEqual(nl.validate_edition(ed), [])


class TestValidate(unittest.TestCase):
    def rebuild(self, ed):
        ed["content_sha256"] = nl.sha256_text(ed["message_text"])
        return ed

    def test_tag_not_last_line(self):
        ed = nl.build_edition(draft())
        ed["message_text"] += "\nP.S."
        self.assertTrue(any("last line" in e for e in nl.validate_edition(self.rebuild(ed))))

    def test_wrong_tag(self):
        ed = nl.build_edition(draft())
        ed["tag"] = "#BS-1012"
        self.assertTrue(any("tag must be" in e for e in nl.validate_edition(ed)))

    def test_legacy_published_file_still_valid(self):
        ed = json.loads((ROOT / "news" / "2026-10-11.json").read_text(encoding="utf-8"))
        self.assertTrue(nl.is_legacy(ed))
        self.assertEqual(nl.validate_edition(ed, "2026-10-11"), [])
        self.assertTrue(nl.validate_edition(ed, "2026-10-11", require_tag=True))

    def test_aside_rules(self):
        for bad in ("估值 250 亿", "看 https://x.com", "（嵌套）", "长" * 41):
            ed = nl.build_edition(draft(tone="cute", asides={0: bad}))
            self.assertTrue(any("aside_zh" in e for e in nl.validate_edition(ed)), bad)

    def test_max_three_asides(self):
        ed = nl.build_edition(draft(tone="cute", asides={0: "a", 1: "b", 2: "c", 3: "d"}))
        self.assertTrue(any("at most 3" in e for e in nl.validate_edition(ed)))

    def test_bad_tone(self):
        ed = nl.build_edition(draft())
        ed["tone"] = "spicy"
        self.assertTrue(any("tone" in e for e in nl.validate_edition(ed)))

    def test_status_is_sent_keyed_by_edition(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "status").mkdir()
            (Path(t) / "status" / "2026-10-11-noon.json").write_text('{"status": "unverified"}')
            self.assertTrue(nl.status_is_sent("2026-10-11-noon", t))
            self.assertFalse(nl.status_is_sent("2026-10-11", t))


class TestPublishPaths(unittest.TestCase):
    def run_pub(self, repo, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "publish_news.py"), *args,
                               "--repo", str(repo), "--no-push", "--date", "2026-10-11"],
                              capture_output=True, text=True)

    def test_noon_does_not_touch_morning(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t)
            (repo / "news").mkdir()
            morning = (ROOT / "news" / "2026-10-11.json").read_text(encoding="utf-8")
            (repo / "news" / "2026-10-11.json").write_text(morning, encoding="utf-8")
            f = repo / "d.json"
            f.write_text(json.dumps(draft("2026-10-11-noon", "cute"), ensure_ascii=False), encoding="utf-8")
            r = self.run_pub(repo, str(f), "--build")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((repo / "news" / "2026-10-11-noon.json").exists())
            self.assertEqual((repo / "news" / "2026-10-11.json").read_text(encoding="utf-8"), morning)

    def test_untagged_new_edition_refused(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t)
            ed = json.loads((ROOT / "news" / "2026-10-11.json").read_text(encoding="utf-8"))
            f = repo / "e.json"
            f.write_text(json.dumps(ed, ensure_ascii=False), encoding="utf-8")
            r = self.run_pub(repo, str(f))
            self.assertEqual(r.returncode, 1)
            self.assertIn("no tag", r.stderr)

    def test_legacy_identical_is_noop(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t)
            (repo / "news").mkdir()
            src = ROOT / "news" / "2026-10-11.json"
            (repo / "news" / "2026-10-11.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            r = self.run_pub(repo, str(src))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("NO-OP", r.stdout)


if __name__ == "__main__":
    unittest.main()
