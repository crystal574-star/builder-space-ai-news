# builder-space-ai-news

UNSW Builder Space 每日 AI 新闻中转仓库。Grok Bot 每天（悉尼时间早上）在 X 上整理 OpenAI、Anthropic、Google DeepMind、NVIDIA 的重要动态，生成 5 条中文摘要，写成 JSON 推送到这里；本地 Windows 发布程序（wx4py）在 09:00 拉取当天文件并通过微信发送。

## 目录

| 路径 | 说明 |
| --- | --- |
| `news/YYYY-MM-DD.json` | 每日一期（悉尼日期），由 `scripts/publish_news.py` 写入 |
| `status/YYYY-MM-DD.json` | 发送结果（sent / verified / failed），由 `scripts/record_status.py` 写入 |
| `schema/news.schema.json` | 新闻 JSON 的 JSON Schema |
| `scripts/` | 云端（Grok Bot 电脑）脚本，只用 Python 标准库 |

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
  "message_text": "可直接发送的完整微信文本，首行为「Builder Space 每日 AI 速递 · 10月11日」",
  "content_sha256": "message_text 的 UTF-8 SHA-256"
}
```

## 用法（云端）

```bash
# 草稿只需 date/items 中的 org、title_zh、summary_zh、source_url、posted_at；--build 自动补全其余字段
python3 scripts/publish_news.py draft.json --build          # 校验 → 写入 news/ → commit → push
python3 scripts/publish_news.py draft.json --build --dry-run
python3 scripts/record_status.py --date 2026-10-11 --status verified --verified --target-mode filehelper --host caroline
```

`publish_news.py` 是幂等的：同一天内容相同则不做任何事；若 `status/` 中该日期已标记为已发送，则拒绝覆盖。

## 安全

- 写入令牌只通过环境变量 `BUILDER_NEWS_GH_TOKEN` 使用，不写入文件、不进 git 历史、不出现在命令行参数里。
- 只收录工具真实返回的来源链接，不编造链接。
- 仓库目前是公开的：不要放任何个人信息、群成员信息或凭证；状态文件只记录结果和错误原因。
- Windows 端默认只发「文件传输助手」；群发需要在本地配置里显式开启并精确指定群名。
