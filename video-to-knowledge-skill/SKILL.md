---
name: video-to-knowledge
description: >-
  短视频/图文链接一键知识化：去水印解析、本地 Whisper 逐字稿、结构化价值萃取、Markdown
  笔记入库 Obsidian。触发词：视频入库、知识化、转笔记、video to knowledge、
  逐字稿入库、内容萃取、发链接入库。
---

# 视频内容知识化 Skill

当用户提供一条**短视频/图文链接**（或含链接的分享文案）并要求入库、知识化、转笔记时，**立即读取并执行本 Skill**，按以下管道（pipeline）全自动完成。

## 前置检查

1. 确认 `config.json` 存在（由 `config_template.json` 复制并填写；或配置 `env_file` 指向 `video-parser/.env`）
2. 确认 `video-parser` 虚拟环境可用：

```bash
# Windows 示例 — 路径按实际项目调整
set PYTHON=D:\0-CryptoLumis\5-automedia\video-parser\.venv\Scripts\python.exe
set SKILL=D:\0-CryptoLumis\5-automedia\video-to-knowledge-skill
set CONFIG=%SKILL%\config.json
```

3. 确认本地转写可用：`video-parser/.env` 中 `TRANSCRIBE_BACKEND=local`，且已安装 ffmpeg 与 faster-whisper（见 `video-parser/requirements.txt`）

---

## 自动化 Pipeline

### 第一步：内容获取

调用 `scripts/video_processor.py`，输入链接，输出结构化 JSON：

```bash
"%PYTHON%" "%SKILL%\scripts\video_processor.py" --config "%CONFIG%" extract "<用户链接或文案>" ^
  --save-raw --output "%TEMP%\v2k_extract.json"
```

**必须拿到：**
- 纯净媒体地址（`media.video_url` 或 `media.images`）
- 元数据（`metadata.title` / `author` / `platform`）
- 带时间戳的完整逐字稿（`transcript.segments` + `transcript.full_text`）

**失败处理：**
- 解析失败 → 报告 `error`，不继续；先查下方「平台解析与故障排除」
- 图集（`media_type: images`）→ 跳过转写，在笔记中记录图片列表
- 转写失败 → 检查 ffmpeg 是否在 PATH 或 `FFMPEG_PATH` 是否配置；GPU 显存不足可改 `WHISPER_DEVICE=cpu` + `WHISPER_MODEL=small`

---

### 第二步：价值萃取

将第一步 JSON 中的 **元数据 + 完整逐字稿**，送入以下 Prompt 进行深度处理（由 Agent 执行，禁止跳过）：

```
# 角色
你是我的顶级知识库架构师，擅长从信息中萃取高密度价值。

# 任务
基于提供的视频信息（标题、作者、平台、逐字稿），生成一份可直接入库的结构化笔记。

# 输出要求（Markdown格式）

## 摘要
用3句话，像给朋友转述一样说清楚核心内容。**禁止使用**“本视频主要围绕…”、“作者分享了…”等模板句式。

## 关键词
5-8个。要求：**具体、可检索、有区分度**。**避免**“内容”、“方法”、“干货”、“视频”这类无效泛义词。

## 内容分类
（单选）教程方法论 / 行业观察 / 个人经验 / 案例拆解 / 观点输出 / 情绪表达

## 核心观点
列出不超过3条。筛选标准：**“如果看完视频只能记住三句话，应该是哪三句？”**

## 金句
直接摘录原文中特别精彩的原话。**如果没有，则写‘无’，严禁编造或拼凑。**

## 价值判断与入库建议
（单选）并简述原因：
- **长期参考**：观点扎实，具备长期复用价值。
- **可二创**：素材新颖，适合作为灵感来源进行二次创作。
- **仅存档**：信息量一般，仅作记录。
- **不建议入库**：内容多为情绪渲染、焦虑营销或低质信息。原因：[简要说明]
```

**输入格式（Agent 内部组装）：**

```markdown
- 平台：{platform}
- 标题：{title}
- 作者：{author}
- 来源：{source_url}
- 逐字稿：
{full_text}
```

---

### 第三步：资产化输出

将第二步萃取结果 + 元数据，整合为**标准 Markdown 笔记**，必须包含 YAML Front-matter：

```markdown
---
title: "{标题}"
date: {YYYY-MM-DD}
source_url: "{原始链接}"
platform: "{平台}"
author: "{作者}"
category: "{内容分类，来自第二步}"
tags: [{关键词1}, {关键词2}, ...]
value_rating: "{长期参考|可二创|仅存档|不建议入库}"
media_type: "{video|images}"
video_url: "{无水印地址，如有}"
created: {ISO8601}
---

# {标题}

> 来源：[{平台}]({source_url}) · {作者} · {date}

{第二步生成的全部章节：摘要、关键词、内容分类、核心观点、金句、价值判断与入库建议}

---

## 逐字稿（带时间戳）

{从 transcript.segments 生成，格式：}
- `[00:00.000 → 00:06.554]` 句子内容

---

## 元数据

| 字段 | 值 |
|------|-----|
| 平台 | {platform} |
| 作者 | {author} |
| 处理时间 | {processed_at} |
| 转写任务 | {task_id} |
```

**若 `value_rating` 为「不建议入库」：** 仍生成笔记但文件名前缀加 `_skip-`，并在索引中标注。

将笔记写入临时文件 `%TEMP%\v2k_note.md`，然后执行归档。

---

### 第四步：自动归档

```bash
"%PYTHON%" "%SKILL%\scripts\video_processor.py" --config "%CONFIG%" archive ^
  --note "%TEMP%\v2k_note.md" ^
  --meta "%TEMP%\v2k_extract.json"
```

**效果：**
- 笔记保存至 `knowledge_base.vault_path`（默认 Obsidian Vault）
- `_content_index.md` 自动追加一行索引

**索引表头（脚本自动创建）：**

| 日期 | 标题 | 平台 | 作者 | 分类 | 标签 | 笔记 |

---

## 一键触发（Agent 执行顺序）

用户发链接并说「入库 / 知识化 / 转笔记」时，Agent **无需逐步询问**，直接：

```
1. extract  → 2. 价值萃取 Prompt → 3. 组装 Front-matter 笔记 → 4. archive
```

完成后向用户报告：
- 笔记保存路径
- 摘要（3 句话版）
- 价值判断结论
- 索引是否已更新

---

## 配置说明

| 配置项 | 说明 |
|--------|------|
| `video_parser_root` | 指向 `video-parser` 目录 |
| `env_file` | 指向 `video-parser/.env`（Whisper / 微信视频号等配置） |
| `knowledge_base.vault_path` | Obsidian 笔记目录 |
| `knowledge_base.index_file` | 索引文件名，默认 `_content_index.md` |

复制配置：

```bash
copy config_template.json config.json
```

---

## 示例

**用户：** `https://weixin.qq.com/sph/AiIFsLYoIF 帮我入库`

**Agent 执行：**
1. `video_processor.py --config config.json extract "https://..." --save-raw -o extract.json`
2. 读取 JSON，运行价值萃取 Prompt
3. 生成带 Front-matter 的 `note.md`
4. `video_processor.py archive --note note.md --meta extract.json`
5. 回复：「已入库 `D:/0-CryptoLumis/5-automedia/YuYe/03-benchmark-accounts/VideoNotes/2026-07-05-如何制作一条高转化的视频.md`」

---

## 平台解析与故障排除

解析逻辑在 `video-parser` 中：`native` 优先 → 失败且平台为 `both` 时自动 `yt-dlp` 兜底。

### 已验证平台策略

| 平台 | backend | 说明 |
|------|---------|------|
| 抖音 | `both` | 原生解析 `_ROUTER_DATA`；失败时 yt-dlp 兜底（yt-dlp 可能需要 Cookie） |
| 快手 | `both` | 同上 |
| 小红书 | `both` | 原生解析 `__INITIAL_STATE__`；失败时 yt-dlp 兜底 |
| 微信视频号 | `native` | 需配置 `WX_SPH_API` 或 `YUANBAO_COOKIE` |

### 已知修复（2026-07-05）

**问题：** 抖音 / 小红书页面内嵌 JSON 含大量空格，旧正则 `(.*?) ` 会在第一个空格处截断，导致 YAML/JSON 解析报错（如 `found unexpected end of stream`）。

**修复：** 两处原生解析器改为匹配到 `</script>` 结束：

```python
# video-parser/parser/native/douyin.py
r"window\._ROUTER_DATA\s*=\s*(.*?)\s*</script>"

# video-parser/parser/native/redbook.py
r"window\.__INITIAL_STATE__\s*=\s*(.*?)\s*</script>"
```

**同步：** `platforms.py` 中抖音、小红书 backend 从 `native` 改为 `both`，原生失败自动走 yt-dlp。

### 常见报错对照

| 报错 / 现象 | 原因 | 处理 |
|-------------|------|------|
| `found unexpected end of stream`（小红书） | 页面 JSON 被正则截断 | 确认 `redbook.py` 已用 `</script>` 结尾正则 |
| `parse video json info from html fail` | 页面结构变更或未登录 | 检查链接是否含有效 `xsec_token`；尝试 yt-dlp 兜底 |
| `FILE_DOWNLOAD_FAILED`（转写） | 视频下载失败 | 检查链接是否有效；本地转写会自动下载到临时目录 |
| 抖音 native 失败 | Cookie 过期或反爬 | `both` 模式会自动尝试 yt-dlp；或更新 Cookie |

### Agent 修复指引

若某平台突然批量解析失败：

1. 用 `extract` 单独测链接，读 `_last_extract.json` 的 `error` 字段
2. 检查 `video-parser/parser/native/` 对应平台文件的正则是否仍匹配 `</script>`
3. 必要时在 `platforms.py` 将该平台 backend 改为 `both`
4. 修复后**同步更新本 Skill 的「已知修复」表**，避免重复踩坑

---

## 注意事项

- 逐字稿默认使用本地 faster-whisper（`TRANSCRIBE_BACKEND=local`），视频下载到本机转写，无云端额度限制
- 金句必须来自原文，禁止编造
- 图集内容无逐字稿时，笔记聚焦图片信息与文案标题
- 密钥勿提交 git；`config.json` 应加入 `.gitignore`
