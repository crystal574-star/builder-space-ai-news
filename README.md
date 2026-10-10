# builder-space-ai-news

UNSW Builder Space 每日 AI 新闻中转仓库。Grok Bot 每天（悉尼时间早上）在 X 上整理 OpenAI、Anthropic、Google DeepMind、NVIDIA 的重要动态，生成 5 条中文摘要，写成 JSON 推送到这里；本地 Windows 发布程序（wx4py）在 09:00 拉取当天文件并通过微信发送。

## 目录

| 路径 | 说明 |
| --- | --- |
| `news/YYYY-MM-DD.json` | 每日一期（悉尼日期），由 `scripts/publish_news.py` 写入 |
| `status/YYYY-MM-DD.json` | 发送结果（sent / verified / failed），由 `scripts/record_status.py` 写入 |
| `schema/news.schema.json` | 新闻 JSON 的 JSON Schema |
| `scripts/` | 云端（Grok Bot 电脑）脚本，只用 Python 标准库：`publish_news.py`、`record_status.py`、`fetch_aihot.py`、`newslib.py` |

## 数据格式（摘要）

```json
{
  "date": "2026-10-11",
  "edition_id": "2026-10-11",
  "generated_at": "2026-10-11T08:40:00+11:00",
  "items": [  // 恰好 5 条
    {"id": "sha256(source_url) 前 16 位", "org": "OpenAI|Anthropic|Google DeepMind|NVIDIA|other",
     "title_zh": "...", "summary_zh": "≤120 字", "source_url": "https://x.com/...", "posted_at": "ISO 时间"}
  ],
  // 可选：origin (x|aihot|x+aihot)、aihot_url (https://aihot.news/story/…)、aihot_rank、aihot_source_count 等
  "message_text": "可直接发送的完整微信文本，首行为「Builder Space 每日 AI 速递 · 10月11日」，末尾为【来源】区和署名",
  "content_sha256": "message_text 的 UTF-8 SHA-256"
}
```

## 用法（云端）

```bash
# 草稿只需 date/items 中的 org、title_zh、summary_zh、source_url、posted_at；--build 自动补全其余字段
python3 scripts/publish_news.py --build draft.json          # 校验 → 写入 news/ → commit → push
python3 scripts/publish_news.py draft.json --build --dry-run
python3 scripts/record_status.py --date 2026-10-11 --status verified --verified --target-mode filehelper --host caroline
```

`publish_news.py` 是幂等的：同一天内容相同则不做任何事；若 `status/` 中该日期已标记为已发送，则拒绝覆盖。

## 每日生成流程（Grok Bot routine）

1. **候选来源**
   - X：@OpenAI @OpenAIDevs @AnthropicAI @GoogleDeepMind @GoogleAI @nvidia @NVIDIAAI 等官方账号最近约 24–36 小时的原创帖（不含回复、转帖）。
   - AIHOT：`python3 scripts/fetch_aihot.py -o /tmp/aihot.json --stories top`。它只请求 `https://aihot.news/api/v1/hot-topics` 和 `/stories/{publicId}`，User-Agent 是 `aihot-api/2.0.0`。只用 aihot.news 域名（aihot.virxact.com 和 `/api/public/*` 于 2026-10-31 停用）。AIHOT 没有数值热度，只记热点榜排名和信源数。
2. **合并去重**：X 帖子和 AIHOT 热点讲的是同一事件（同一公司、同一发布，或 AIHOT 的 sourceNames 里有该官方账号）时合并为一条，`origin` 记为 `x+aihot`。原文优先用官方帖或官方页面，同时附 AIHOT 阅读页和排名。
3. **挑选 5 条**：先按 AIHOT 排名，再看官方帖互动量。四家公司以外（`org: "other"`，消息里显示为【业界】）最多 2 条，而且只收 AIHOT 排名很靠前的。
4. **只用真实数据**：链接、数字、引述都必须来自工具真实返回的内容，不编造。摘要 1–2 句，不超过 120 字。
5. **格式（简报式）**：正文只放「编号 + 【机构】标题 + 摘要」；末尾是「——」和【来源】区，按编号列出「原文 <url>」和「AIHOT <url>（热点榜第 N）」，最后是署名「来源：X 公开动态、AIHOT（aihot.news）」。这些都由 `--build` 自动生成。
6. **发布**：草稿 JSON 只需要 `date`，以及每条的 `org/title_zh/summary_zh/source_url/posted_at`，可选 `aihot_url/aihot_rank/aihot_*_count/aihot_id`。

```bash
python3 scripts/publish_news.py --build <draft.json>                 # 校验 → news/YYYY-MM-DD.json → commit → push
python3 scripts/publish_news.py --build <draft.json> --dry-run       # 只预览
```

AIHOT 使用规则（https://aihot.news/terms）：个人非商业、公益非商业和组织内部使用免费，须保留来源和原文链接；对外商业使用或批量公开再分发，须先向 wzglyay@virxact.com 申请书面授权。

## 安全

- 写入令牌只通过环境变量 `BUILDER_NEWS_GH_TOKEN` 使用，不写入文件、不进 git 历史、不出现在命令行参数里。
- 只收录工具真实返回的来源链接，不编造链接。
- 仓库目前是公开的：不要放任何个人信息、群成员信息或凭证；状态文件只记录结果和错误原因。
- Windows 端默认只发「文件传输助手」；群发需要在本地配置里显式开启并精确指定群名。
