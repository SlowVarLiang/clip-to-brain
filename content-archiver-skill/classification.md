# 内容分类决策树

Agent 必须在归档前完成分类，并**向用户简要说明分类理由**（1-2 句）。一条素材可归属主类 + 副类；**主类决定归档目录**，副类写入 frontmatter `secondary_categories` 并在正文「关联」段双链。

## 七类判定（按优先级从高到低匹配）

### 01 · personal-experience

**信号：** 第一人称经历、「我做过/踩坑/交付/客户反馈」、项目复盘、个人判断、Before→After 来自自身实践。

**子目录：**
| 子目录 | 何时用 |
|--------|--------|
| `project-retrospectives` | 完整项目复盘 |
| `lessons-learned` | 踩坑、失败、教训 |
| `client-cases` | 服务客户的真实案例 |
| `personal-judgments` | 基于经验的立场与选择 |

**排除：** 转述他人教程 → 02 或 03；纯用户提问 → 05。

---

### 02 · industry-resources

**信号：** 第三方客观信息、行业报告、趋势数据、工具官方文档、商业模式分析、政策/平台改版新闻。

**子目录：** `trend-reports` / `tool-docs` / `business-models` / `industry-news`

**排除：** 他人账号内容结构拆解 → 03；可执行的选题角度 → 04。

---

### 03 · benchmark-accounts

**信号：** **具体**他人账号/笔记，需拆标题/封面/选题/结构/转化；短视频/图文链接默认先进 `VideoNotes`（保留原文）。

**子目录：**
| 子目录 | 何时用 |
|--------|--------|
| `VideoNotes` | 视频/图文链接经 video-to-knowledge 流水线入库 |
| `_benchmark` | 针对某条笔记/某个账号的手工拆解 |
| `account-profiles` | 按账号汇总规律 |

**排除：** 通用公式（封面三公式、12种封面类型）→ 04/methodology；B2B 行业方法论 → 02。

**链接默认策略：** 抖音/小红书/视频号/B站等 → 先走 video-to-knowledge → 归档到 `03` + `VideoNotes`；若提炼为通用公式则改归档 04。

---

### 04 · viral-topics

**信号：** 选题灵感、标题公式、已被验证的内容方向、可复用的内容骨架；**平台运营方法论**；**官方优质内容标准**。

**子目录：**
| 子目录 | 何时用 |
|--------|--------|
| `platform-ops` | 涨粉、粉丝维护、内容调优、变现模式 |
| `content-standards` | 官方/垂类优质内容标准、内容进阶指南 |
| `methodology` | 封面类型库、标题公式（通用、不绑定具体账号） |
| `efficiency` / `money-making` / `pitfalls` / `tool-tutorials` | 按选题方向 |

**排除：** 具体笔记拆解 → 03；合规红线 → 07。

---

### 05 · user-questions

**信号：** 用户原话提问、评论区/私域/社群/客户反馈、以问号或困惑为主、适合反向生成选题。

**子目录：** `comments` / `private-consulting` / `community` / `client-feedback`

**技巧：** 保留用户原话；推断「表面问题 vs 真实诉求」。

---

### 06 · product-info

**信号：** 课程/服务/咨询介绍、交付方式、适合人群、价格、转化话术、产品 FAQ。

**子目录：** `courses` / `services` / `pricing` / `conversion-scripts`

---

### 07 · platform-rules

**信号：** 某平台**合规红线**：审核规则、社区规范/公约、敏感词、引流限制、原创保护、不当营销禁令、违规案例。

**子目录：** `xiaohongshu` / `douyin` / `channels`（按平台选）

**排除：** 涨粉/粉丝/调优/变现教程 → 04/platform-ops；垂类优质标准 → 04/content-standards；封面公式 → 04/methodology。

---

## 输入类型路由

| 输入 | 第一步 | 默认主类 |
|------|--------|----------|
| 短视频/图文链接 | video-to-knowledge `extract` → 价值萃取 | `03` / `VideoNotes` |
| **H5 长图链接** | `h5_image_pipeline.py pipeline` → OCR 文本 | 通常 `07` / 平台规则 |
| 文章/网页链接 | WebFetch 抓取正文 | 按内容判定 01-07 |
| 纯文字 | 直接分类 | 按内容判定 01-07 |
| 用户明确指定类别 | 尊重用户 | 用户指定 |

## 边界案例

| 情况 | 处理 |
|------|------|
| 他人教程链接 | 主类 `03`；工具知识点可副类 `02` |
| 用户问「Codex 怎么用」 | `05` / `comments` 或 `private-consulting` |
| 「我帮客户用 Codex 省了 3 天」 | `01` / `client-cases` |
| 行业白皮书 PDF 摘要 | `02` / `trend-reports` |
| 小红书限流词列表 | `07` / `xiaohongshu` |
| 小红书创作学院「极速涨粉」 | `04` / `platform-ops` |
| 小红书创作学院「美妆垂类优质标准」 | `04` / `content-standards` |
| 12种爆款封面（通用类型库） | `04` / `methodology` |
| 某博主单条封面教程（VideoNotes） | `03` / `VideoNotes` |
| 标题「10 分钟学会 XX」灵感 | `04` / `tool-tutorials` |

## 模板选择

| 主类 | 模板文件 |
|------|----------|
| 01 | `YuYe/01-personal-experience/_template.md` |
| 02 | `YuYe/02-industry-resources/_template.md` |
| 03 拆解 | `YuYe/03-benchmark-accounts/_template-benchmark.md` |
| 03 视频 | video-to-knowledge 标准笔记格式 |
| 04 | `YuYe/04-viral-topics/_template.md` |
| 05 | `YuYe/05-user-questions/_template.md` |
| 06 | `YuYe/06-product-info/_template.md` |
| 07 | `YuYe/07-platform-rules/_template.md` |
