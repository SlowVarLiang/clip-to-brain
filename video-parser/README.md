# 视频去水印解析工具

支持 **80+ 短视频/图集平台**，粘贴链接自动解析无水印视频地址。

## 支持平台

| 类别 | 平台 |
|------|------|
| 国内短视频 | 抖音、快手、小红书、微博、微视、皮皮虾、皮皮搞笑、最右、西瓜、今日头条、火山、度小视、好看视频、梨视频、美拍、全民K歌 等 |
| 长视频 | 哔哩哔哩、AcFun、腾讯视频、搜狐、央视网、新片场、虎牙、六间房 |
| 音乐社交 | 网易云音乐、酷狗、酷我、唱吧、YY、陌陌、全民K歌 |
| 国际 | TikTok、YouTube、Twitter/X、Instagram、Facebook、Vimeo、Reddit |
| 其他 | 知乎、腾讯新闻、人民日报、开眼、懂车帝、趣头条、剪映、京东/淘宝/天猫/拼多多 等 |

> 未在列表中的链接会自动尝试 **yt-dlp** 通用解析（1800+ 站点兜底）。

## 快速开始

```bash
cd video-parser

# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 安装依赖
pip install -r requirements.txt

# 复制环境变量（可选，微博/TikTok 等需要）
copy .env.example .env
```

## 使用方式

### 1. 交互模式（推荐）

```bash
python main.py
```

粘贴分享链接或整段文案，回车即可解析：

```
链接> 7.48 复制打开抖音 https://v.douyin.com/xxxxx/ ...
```

### 2. 命令行单次解析

```bash
python main.py "https://v.douyin.com/xxxxx"
python main.py --json "https://www.bilibili.com/video/BVxxxx"
```

### 3. 解析并下载

```bash
python main.py -d "https://v.douyin.com/xxxxx"
python main.py -d -o ./my-videos "链接"
```

### 4. Web 界面（解析 + 逐字稿）

```bash
python main.py --serve
# 浏览器打开 http://localhost:8765
```

1. 粘贴分享链接 → 点击「解析视频」
2. 解析成功后 → 点击「转为逐字稿」
3. 自动调用本地 Whisper 转写，完成后展示带时间戳的文稿

### 5. HTTP API 服务

```bash
python main.py --serve
# 默认 http://0.0.0.0:8765
```

```bash
# GET 请求
curl "http://localhost:8765/parse?url=https://v.douyin.com/xxxxx"

# POST 请求（支持整段分享文案）
curl -X POST http://localhost:8765/parse -d "text=7.48 复制打开抖音 https://v.douyin.com/xxxxx"

# 转为逐字稿（异步，返回 job_id 后轮询）
curl -X POST http://localhost:8765/transcribe \
  -H "Content-Type: application/json" \
  -d '{"video_url":"https://无水印视频地址.mp4"}'

curl http://localhost:8765/transcribe/{job_id}
```

返回 JSON 示例：

```json
{
  "success": true,
  "platform": "抖音",
  "title": "视频标题",
  "author": "作者昵称",
  "video_url": "https://无水印视频地址.mp4",
  "cover_url": "https://封面.jpg",
  "images": [],
  "media_type": "video",
  "backend": "native"
}
```

## 解析引擎

| 引擎 | 说明 |
|------|------|
| **native** | 内置原生解析器，覆盖 **抖音、快手、小红书、哔哩哔哩**（含图集/LivePhoto） |
| **ytdlp** | [yt-dlp](https://github.com/yt-dlp/yt-dlp) 兜底，覆盖 YouTube/TikTok/知乎/微博/西瓜等 **1800+ 站点** |

解析策略：**native 优先 → yt-dlp 兜底**。

> 可选：安装 [parse-video-py](https://github.com/wujunwei928/parse-video-py) 可扩展更多国内平台原生解析（皮皮虾、微视、好看视频等）。

## 逐字稿（本地 Whisper / 可选阿里云）

支持两种后端，在 `.env` 中切换 `TRANSCRIBE_BACKEND`：

| 后端 | 说明 |
|------|------|
| `local`（默认） | 本地 faster-whisper + ffmpeg，**无额度限制**，视频下载到本机转写 |
| `aliyun` | 阿里云录音文件识别，需公网可访问视频 URL，有额度限制 |

### 本地转写（推荐）

**依赖：**
1. [ffmpeg](https://ffmpeg.org/download.html) 已加入 PATH（或配置 `FFMPEG_PATH`）
2. `pip install -r requirements.txt`（含 faster-whisper、CUDA 运行时）

```env
TRANSCRIBE_BACKEND=local
WHISPER_MODEL=medium          # 中文推荐 medium
WHISPER_LANGUAGE=zh
WHISPER_DEVICE=cuda           # RTX 3070 等 NVIDIA 显卡
WHISPER_COMPUTE_TYPE=float16
```

首次运行会自动下载模型（medium 约 1.5GB）。5 分钟中文视频，GPU 约 30 秒–2 分钟。

### 阿里云（可选）

若需切换回云端转写，在 `.env` 中设置 `TRANSCRIBE_BACKEND=aliyun` 并填写密钥，详见 `.env.example` 注释段。

## 环境变量

| 变量 | 说明 |
|------|------|
| `WEIBO_COOKIE` | 微博解析 Cookie（可选） |
| `HTTP_PROXY` / `HTTPS_PROXY` | TikTok/YouTube 等海外平台代理 |
| `API_HOST` / `API_PORT` | API 服务地址和端口 |
| `TRANSCRIBE_BACKEND` | 转写后端：`local`（默认）或 `aliyun` |
| `WHISPER_MODEL` / `WHISPER_DEVICE` | 本地 Whisper 模型与设备 |
| `FFMPEG_PATH` | ffmpeg 可执行文件路径（PATH 未生效时） |
| `YUANBAO_COOKIE` | 微信视频号解析 Cookie（可选） |

## 注意事项

- 部分平台接口会变更，解析失败时请更新依赖：`pip install -U yt-dlp`
- 微信公众号视频号、部分加密直播流不在支持范围内
- 请遵守各平台服务条款，仅用于个人学习研究
