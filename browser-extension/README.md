# YuYe 视频归档 · 浏览器插件

刷 **YouTube / B站** 时，点按钮即可：解析 → Whisper 转写 → 写入 YuYe（主笔记 + `_transcripts/` 逐字稿）。

## 前置条件

1. 本机已启动 `video-parser` API（默认 `http://127.0.0.1:8765`）
2. `.env` 本地自用保持 `REQUIRE_API_KEY=false`（**无需 API Key**）
3. 若将来对外部署并开启 Key 验证，再在插件「高级」里填写

启动 API：

```powershell
cd D:\0-CryptoLumis\5-automedia\video-parser
.\.venv\Scripts\python.exe -m parser.server
```

## 安装（Chrome / Edge）

1. 打开 `chrome://extensions` 或 `edge://extensions`
2. 开启 **开发者模式**
3. **加载已解压的扩展程序** → 选择本目录 `browser-extension/`
4. 点击扩展图标 → 填 API 地址 → **测试连接**（API Key 留空即可）

## 使用方式

| 方式 | 说明 |
|------|------|
| 浮动按钮 | 视频页右下角 **YuYe 归档** |
| 扩展 Popup | **归档当前标签页** |
| 右键菜单 | 页面 / 视频上 → **归档当前视频到 YuYe** |

提交后扩展会轮询 `GET /ingest/{job_id}`，完成后系统通知显示笔记路径。

## API 端点（服务端）

```http
POST /ingest
{ "url": "https://www.youtube.com/watch?v=..." }

GET /ingest/{job_id}
```

长视频转写可能数分钟，请保持 API 进程运行。

## 局域网 GPU 机

Popup 保存 API 地址为 `http://192.168.x.x:8765` 时，浏览器会请求访问该主机权限。

## 已知限制

- **YouTube bot 验证**：服务端需配置 yt-dlp cookies（`--cookies-from-browser`），否则可能解析失败
- **小红书 / 抖音**：MVP 未支持 DOM 取链，后续版本可加
- 任务状态存在内存中，**重启 API 会丢失进行中的 job_id**

## 目录结构

```
browser-extension/
  manifest.json    # MV3
  background.js    # 调 API + 轮询 + 通知
  content.js       # 浮动按钮 + URL 提取
  popup.html/js    # 设置与手动归档
```
