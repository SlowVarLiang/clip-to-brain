# Clip-to-Brain

**粘贴链接 → 结构化 Obsidian 笔记 + 可写角度 + 选题卡**

开源自托管版。数据在本地，LLM 用你自己的 Key。

![Hero](../docs/assets/clip-to-brain-hero.png)

![Demo GIF](../docs/assets/clip-to-brain-demo.gif)

---

## 5 分钟安装（Windows）

### 1. 前置

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) 在 PATH 中
- Obsidian（可选，推荐）

### 2. 一键初始化

```powershell
cd clip-to-brain
.\setup.ps1
```

脚本会：

- 创建 `video-parser` 虚拟环境并安装依赖
- 复制 `.env.example` → `../.env.local`（需填写 `LLM_API_KEY`）
- 初始化 Obsidian 知识库 → `../vault/`
- 生成 `content-archiver-skill/config.json`

### 3. 编辑 LLM Key

```powershell
notepad ..\.env.local
```

推荐 DeepSeek（便宜、中文好）：

```env
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

### 4. 第一条链接

```powershell
cd ..\content-archiver-skill
.\clip.ps1 "https://weixin.qq.com/sph/..."
```

成功回执：

```
✅ 已入库
📁 03-benchmark-accounts/VideoNotes/...
💡 创作者可写：
   - ...
📝 选题卡：04-viral-topics/_inbox/...
```

### 5. Obsidian

用 Obsidian 打开 `vault/` 文件夹（Vault 名建议 `YuYe`）。

---

## 5 分钟安装（macOS / Linux）

```bash
cd clip-to-brain
chmod +x setup.sh
./setup.sh

# 编辑 Key
nano ../.env.local

# 归档
cd ../content-archiver-skill
python scripts/clip.py "https://..."
```

---

## Docker

```bash
# 1. 准备配置
cp clip-to-brain/.env.example .env.local
# 编辑 LLM_API_KEY

# Docker 使用 clip-to-brain/config.docker.json（compose 已挂载）

# 2. 启动
cd clip-to-brain
docker compose up -d --build

# 3. Dashboard
open http://127.0.0.1:8765/clip/dashboard
```

---

## 支持的输入

| 输入 | 示例 |
|------|------|
| 视频号 / 小红书 / B站 / 抖音 | `https://weixin.qq.com/sph/...` |
| 微信公众号 | `https://mp.weixin.qq.com/s/...` |
| 纯文本（≥80字） | 长文粘贴 |

```powershell
.\clip.ps1 -InputFile article.txt
.\clip.ps1 -Stats
.\clip.ps1 -ListProfiles
```

---

## Profile（创作者人设）

`content-archiver-skill/profiles/` 下 YAML 文件，控制二创角度风格：

| Profile | 适用 |
|---------|------|
| `default-creator` | 通用创作者（默认） |
| `tutorial-blogger` | AI 教程博主 |
| `industry-researcher` | 行业研究，不生成选题卡 |
| `yuye` | 予野原版人设 |

```powershell
.\clip.ps1 "<链接>" -Profile tutorial-blogger
```

自定义：复制 `default-creator.yaml` 改 `label` / `persona`。

---

## 可选：Telegram 丢链

```powershell
# .env.local 添加 TELEGRAM_BOT_TOKEN
.\start-telegram.ps1
```

Bot 里直接发链接，无需 webhook。

---

## 可选：API + Dashboard + Chrome 扩展

```powershell
.\start-clip.ps1
# http://127.0.0.1:8765/clip/dashboard
```

![Dashboard](../docs/assets/clip-to-brain-dashboard.png)

Chrome 扩展：`browser-extension/` → 加载 unpacked → 刷视频页点「丢链归档」。

---

## 项目结构

```
clip-to-brain/           ← 你在这里（安装入口）
content-archiver-skill/  ← Clip 引擎 + profiles + vault 模板
video-parser/            ← 80+ 平台解析 + API
video-to-knowledge-skill/ ← 转写
vault/                   ← 默认 Obsidian 知识库（setup 生成）
browser-extension/       ← Chrome 插件
```

---

## 常见问题

**小红书失败？**  
分享链须含 `xsec_token`，从 App 重新复制完整链接。

**没有 LLM Key？**  
设置 `USE_MOCK_AI=true` 可跑通流程，但摘要质量差。

**转写很慢？**  
首次运行会下载 Whisper 模型。有 NVIDIA GPU 可在 `.env` 调 `WHISPER_MODEL=medium`。

---

## License

MIT — 见 [LICENSE](LICENSE)

---

## 与商业版关系

本仓库为 **开源自托管**。云端托管、多用户、按量计费版后续单独提供。
