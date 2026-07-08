---
name: content-archiver
description: >-
  Lumis 内容自动识别与归档：用户发送文字或链接，识别内容类型，写入
  lumis/ 七类知识库对应文件夹。触发词：内容归档、整理入库、自动分类、
  lumis入库、发链接归档、发文字入库、content archiver、知识库归档。
---

# Lumis 内容自动归档 Skill

用户提供**文字或链接**并要求入库、归档、整理、分类时，**立即读取并执行本 Skill**。目标：识别内容 → 选定 lumis 分类 → 生成结构化笔记 → 写入对应文件夹 → 更新总索引。

## 前置检查

1. 确认 `content-archiver-skill/config.json` 存在（由 `config_template.json` 复制）
2. 路径变量（Windows 示例，按实际项目调整）：

```bash
set PYTHON=python
set ARCHIVER=D:\0-CryptoLumis\5-automedia\content-archiver-skill
set CONFIG=%ARCHIVER%\config.json
set LUMIS=D:\0-CryptoLumis\5-automedia\lumis
```

3. 若输入为**短视频/图文链接**，还需 `video-to-knowledge-skill` 可用（本地 Whisper 转写已配置）
4. 若输入为 **H5 长图页**，需安装 OCR 依赖：`pip install -r requirements-ocr.txt`（见 [h5-image-ocr.md](h5-image-ocr.md)）

---

## 自动化 Pipeline

```
输入（文字/链接）
  → ① 获取内容
  → ② 分类判定（见 classification.md）
  → ③ 选模板 + 结构化萃取
  → ④ content_archiver.py archive
  → ⑤ 向用户报告路径与分类理由
```

**Agent 无需逐步询问**，除非：内容无法判定主类、或 `value_rating` 为「不建议入库」需用户确认。

---

### 第一步：获取内容

**A. 链接 — 视频/图文平台（抖音、小红书、视频号、快手、B站等）**

→ 调用 **video-to-knowledge** Skill 完成 `extract` + 价值萃取 + 笔记组装（见 `../video-to-knowledge-skill/SKILL.md`）。

默认归档：`category=03`，`subfolder=VideoNotes`。

若用户明确说「这是我自己的经历/案例」→ 主类改 `01`，仍可用 extract 获取逐字稿，但模板换 `01-personal-experience/_template.md`。

**B. 链接 — H5 长图页（无可选文字，内容在图片中）**

识别特征：`fe.xiaohongshu.com/ditto`、`xiaohongshu.com/crown`，或 WebFetch 正文为空但含多张 CDN 图。

→ 执行 **H5 长图 OCR 流水线**（详见 [h5-image-ocr.md](h5-image-ocr.md)）：

```bash
"%PYTHON%" "%ARCHIVER%\scripts\h5_image_pipeline.py" pipeline "<url>" -o "%TEMP%\h5_pipeline.json"
```

若 `need_browser: true` → 用 browser CDP 提取 `img.src` → `--urls-json` 重跑。

读取输出中的 `full_text` / `ocr_path`，进入第二步分类 + 第三步结构化。

默认分类：平台官方文档 → `07` / `xiaohongshu`；创作学院垂类标准 → 同上。

**C. 链接 — 普通网页/文章**

→ 使用 WebFetch 抓取正文 + 提取标题；失败则尝试 **B**（长图 OCR），仍失败则请求用户粘贴正文。

**D. 纯文字**

→ 直接进入第二步分类。

---

### 第二步：分类判定

**必读** [classification.md](classification.md)，输出内部结构：

```json
{
  "primary_category": "03",
  "subfolder": "_benchmark",
  "secondary_categories": ["02"],
  "reason": "他人发布的 Codex 教程，适合对标拆解；工具点可副类归档到行业资料"
}
```

向用户展示 `reason`（1-2 句）。

---

### 第三步：结构化萃取

按主类选模板（路径相对于 `lumis/`），填充 frontmatter + 正文。**禁止空泛总结**；金句/用户原话必须来自原文。

**通用 frontmatter（所有类别必填）：**

```yaml
---
title: ""
date: YYYY-MM-DD
source_url: ""
source_type: link | text | video
lumis_category: "01"           # 主类编号
lumis_subfolder: "lessons-learned"
secondary_categories: []         # 可选，如 ["02"]
tags: []
created: ISO8601
---
```

**视频笔记（03/VideoNotes）** 额外字段：`platform`, `author`, `value_rating`, `transcript_note` — 与 video-to-knowledge 保持一致。

**一键入库流程（`lumis_ingest.py` / `ingest.ps1`）：**

1. 解析 + 转写
2. **完整逐字稿** → `_transcripts/{date}-{title}-transcript.md`
3. **主笔记** → 萃取内容 + `## 逐字稿` 一行链接（不重复粘贴全文）
4. 长短视频自动分流：
   - 短视频（<10min）：[value_extraction_short.md](prompts/value_extraction_short.md) 结构
   - 长视频（≥10min）：[value_extraction_long.md](prompts/value_extraction_long.md) 结构（含章节脉络、实操要点、工具表）

Cursor Agent 手动归档时，同样遵循：**逐字稿独立文件，主笔记只链接**。

**价值判断（视频/长文必做）：**

- **长期参考** / **可二创** / **仅存档** / **不建议入库**

若为「不建议入库」→ 文件名前缀 `_skip-`，并询问用户是否仍归档。

---

### 第四步：自动归档

将笔记写入 `%TEMP%\lumis_note.md`，执行：

```bash
"%PYTHON%" "%ARCHIVER%\scripts\content_archiver.py" --config "%CONFIG%" archive ^
  --note "%TEMP%\lumis_note.md" ^
  --category "<01-07>" ^
  --subfolder "<subfolder>"
```

查看输出 JSON 中的 `note_path`、`relative_path`。

**副类处理：** 若 `secondary_categories` 非空，为副类生成精简摘要笔记（5-10 行 + 双链主笔记），再各执行一次 `archive`。

---

### 第五步：回复用户

报告：

1. **归档路径**（相对 `lumis/` 即可）
2. **主类 + 子目录**（中文库名 + 英文文件夹名）
3. **分类理由**（1-2 句）
4. **摘要**（3 句话）
5. 总索引已更新：`lumis/_content_index.md`

---

## 分类速查

| 编号 | 文件夹 | 一句话 |
|------|--------|--------|
| 01 | `01-personal-experience` | 我自己的经历、案例、判断 |
| 02 | `02-industry-resources` | 行业客观资料、报告、工具文档 |
| 03 | `03-benchmark-accounts` | 对标账号/他人内容拆解 |
| 04 | `04-viral-topics` | 验证过的选题与标题方向 |
| 05 | `05-user-questions` | 用户/客户提出的问题 |
| 06 | `06-product-info` | 产品、课程、价格、转化 |
| 07 | `07-platform-rules` | 平台规则与审核风险 |

完整决策树 → [classification.md](classification.md)

查看脚本支持的子目录：

```bash
"%PYTHON%" "%ARCHIVER%\scripts\content_archiver.py" --config "%CONFIG%" routes
```

---

## 示例

### 例 1：视频链接

**用户：** `https://v.douyin.com/xxx 帮我归档`

1. video-to-knowledge：`extract` → 萃取 → 组装笔记
2. 分类：`03` / `VideoNotes`（他人教程）
3. `content_archiver.py archive --category 03 --subfolder VideoNotes`
4. 回复：「已归档至 `03-benchmark-accounts/VideoNotes/2026-07-06-xxx.md`」

### 例 2：用户提问文字

**用户：** `有人问：Codex 和 Cursor 到底选哪个？`

1. 分类：`05` / `comments`（或 `private-consulting`）
2. 用 `05-user-questions/_template.md` 填写，保留原话
3. `archive --category 05 --subfolder comments`
4. 建议：「可映射选题 → [[04-viral-topics/tool-tutorials/...]]」

### 例 3：个人踩坑

**用户：** `上周帮客户部署 Codex，权限模式开太高差点删库，最后改成默认权限才稳`

1. 分类：`01` / `lessons-learned`
2. 用 `01-personal-experience/_template.md`
3. `archive --category 01 --subfolder lessons-learned`

---

### 例 4：H5 长图（社区公约）

**用户：** `https://fe.xiaohongshu.com/ditto/vincent/... 归档`

1. `h5_image_pipeline.py pipeline "<url>"`（必要时 browser 取图 + `--urls-json`）
2. 读 `full_text` → 分类 `07` / `xiaohongshu`
3. 结构化笔记 → `content_archiver.py archive --category 07 --subfolder xiaohongshu`
4. 回复归档路径 + OCR 页数

---

## 与 video-to-knowledge 的分工

| Skill / 脚本 | 职责 |
|-------|------|
| video-to-knowledge | 链接解析、逐字稿、视频笔记格式、VideoNotes 原始素材 |
| **h5_image_pipeline.py** | H5 长图：提取 URL → 下载 → RapidOCR → 合并文本 |
| content-archiver（本 Skill） | **七库分类路由**、模板选择、总索引 `_content_index.md` |

视频链接：**两个 Skill 串联** — 先 video-to-knowledge 生成笔记，再 content-archiver 确认分类并 `archive`（默认 03/VideoNotes）。

若 video-to-knowledge 的 `archive` 已写入 VideoNotes，content-archiver 只需**补写总索引**或跳过重复写入（检查目标路径是否已存在）。

---

## 注意事项

- 分类不确定时，**宁可问一句**，不要默认丢进 `02`
- 用户原话、金句禁止编造
- 密钥与 `config.json` 勿提交 git
- 文件夹名一律英文（见 `lumis/README.md`）
