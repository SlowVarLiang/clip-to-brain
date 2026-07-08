# 价值萃取提示词（自动路由）

- **短视频**（<10min）：[value_extraction_short.md](value_extraction_short.md)
- **长视频**（≥10min）：[value_extraction_long.md](value_extraction_long.md)

`lumis_ingest.py` 会按视频时长自动选用对应结构生成主笔记；完整逐字稿始终写入 `_transcripts/*-transcript.md`，主笔记仅保留链接。
