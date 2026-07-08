# H5 长图 OCR 流水线

适用于官方 H5 长图页（如小红书社区公约、创作学院图文），页面无可选文字、内容全在图片中。

## 依赖安装（首次）

```bash
pip install -r requirements-ocr.txt
```

## 检测条件

满足任一即走本流水线（而非 WebFetch）：

- URL 匹配 `fe.xiaohongshu.com/ditto`、`xiaohongshu.com/crown` 等（见 `config.json` → `h5_image.url_patterns`）
- WebFetch / `document.body.innerText` 为空或极短，但页面含多张 `xhscdn` 图片

## 一键流水线

```bash
"%PYTHON%" "%ARCHIVER%\scripts\h5_image_pipeline.py" pipeline "<url>" -o "%TEMP%\h5_pipeline.json"
```

**若返回 `"need_browser": true`**（JS 渲染页），先用浏览器取图：

```javascript
// browser_cdp → Runtime.evaluate
JSON.stringify([...document.querySelectorAll('img')].map(i => i.src).filter(s => s.includes('xhscdn')))
```

将结果存为 `%TEMP%\browser_urls.json`（格式 `{"urls": [...]}` 或 `[...]`），再执行：

```bash
"%PYTHON%" "%ARCHIVER%\scripts\h5_image_pipeline.py" pipeline "<url>" ^
  --urls-json "%TEMP%\browser_urls.json" ^
  -o "%TEMP%\h5_pipeline.json"
```

## 输出

| 字段 | 说明 |
|------|------|
| `ocr_path` | 原始 OCR Markdown（`_ocr_temp/ocr_raw.md`） |
| `full_text` | 合并纯文本，供 Agent 结构化 |
| `download.files` | 下载的图片路径列表 |

## Agent 后续步骤

1. 读取 `full_text` 或 `ocr_raw.md`
2. 按 [classification.md](classification.md) 分类（平台规则类通常 → `07` / `xiaohongshu`）
3. 结构化萃取 → 写入 `%TEMP%\YuYe_note.md`
4. `content_archiver.py archive --category 07 --subfolder xiaohongshu`

## OCR 引擎

默认 **RapidOCR**（`rapidocr-onnxruntime`），中文长图识别效果良好。

降级方案：若 OCR 依赖未安装，Agent 用 **Read 工具**逐张读取 `_ocr_temp/page-*.jpg`（视觉识别，精度更高但较慢）。

## 分步命令

```bash
# 仅提取 URL
python scripts/h5_image_pipeline.py extract-urls "<url>" -o urls.json

# 仅下载
python scripts/h5_image_pipeline.py download --urls urls.json --dir _ocr_temp

# 仅 OCR
python scripts/h5_image_pipeline.py ocr --dir _ocr_temp --output ocr_raw.md --print-text
```
