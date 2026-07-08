# Clip-to-Brain v0.1.0

**首个开源自托管版本** — 粘贴链接，本地生成 Obsidian 结构化笔记。

---

## Highlights

### 统一入口 `clip.py`

一条命令处理视频号、小红书、B站、抖音、公众号、纯文本：

```powershell
.\clip.ps1 "https://weixin.qq.com/sph/..."
```

回执包含：笔记路径、价值评级、二创角度、选题卡路径。

### Profile 人设体系

不再硬编码单一博主，内置 4 套 Profile，支持 YAML 自定义：

| Profile | 说明 |
|---------|------|
| `default-creator` | 通用创作者（新用户默认） |
| `tutorial-blogger` | AI 教程博主口吻 |
| `industry-researcher` | 行业研究，偏深度检索 |
| `yuye` | 予野原版人设（示例） |

### Obsidian 知识库

- `setup.ps1` / `setup.sh` 一键初始化 `vault/`
- 笔记含 YAML frontmatter、摘要、关键词、评级
- 高价值内容自动生成选题卡 → `04-viral-topics/_inbox/`

### 可选扩展

- **REST API** + **Dashboard**（`start-clip.ps1`）
- **Telegram 长轮询 Bot**（无需 webhook）
- **Chrome 扩展**（刷视频页一键丢链）
- **Docker** 一键部署

---

## 安装

见 [README.md](../README.md) 或 [clip-to-brain/README.md](README.md)

---

## 已知限制

- 小红书链接须含完整 `xsec_token`
- 首次转写需下载 Whisper 模型，耗时较长
- H5 长图 OCR 暂不支持，会明确报错
- 需自备 LLM API Key（推荐 DeepSeek）

---

## 升级路径（v0.2 规划）

- [ ] 更多 Profile 模板包
- [ ] 一键 Obsidian 插件
- [ ] 云端托管 Telegram SaaS
- [ ] 批量导入 / RSS 订阅

---

## 致谢

从个人「予野素材机」工作流提炼，感谢早期真实归档链路验证。
