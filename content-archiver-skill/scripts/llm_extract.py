"""MiniMax / OpenAI 兼容 API — 视频笔记价值萃取。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILES = (
    SKILL_ROOT.parent / ".env.local",
    SKILL_ROOT.parent / ".env",
    SKILL_ROOT / ".env.local",
    SKILL_ROOT / ".env",
)

SECTION_ORDER_SHORT = (
    "摘要",
    "关键词",
    "内容分类",
    "核心观点",
    "金句",
    "价值判断与入库建议",
)
SECTION_ORDER_LONG = SECTION_ORDER_SHORT[:3] + (
    "章节脉络",
    "核心观点",
    "实操要点",
    "工具与概念",
    "金句",
    "价值判断与入库建议",
)


@dataclass
class ValueExtractionResult:
    suggested_title: str | None = None
    sections: dict[str, str] = field(default_factory=dict)
    raw_markdown: str = ""
    long_video: bool = False


def _load_env_files() -> None:
    for path in DEFAULT_ENV_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def llm_settings(config: dict[str, Any]) -> dict[str, Any]:
    _load_env_files()
    ingest = config.get("ingest", {})
    use_mock = os.getenv("USE_MOCK_AI", "").strip().lower() in ("1", "true", "yes")
    api_key = os.getenv("LLM_API_KEY", "").strip()
    enabled = ingest.get("llm_enabled", True) and not use_mock and bool(api_key)
    return {
        "enabled": enabled,
        "api_key": api_key,
        "base_url": os.getenv("LLM_BASE_URL", "https://api.minimax.chat/v1").rstrip("/"),
        "model": os.getenv("LLM_MODEL", "MiniMax-Text-01"),
        "provider": os.getenv("LLM_PROVIDER", "minimax"),
        "max_transcript_chars": int(ingest.get("llm_max_transcript_chars", 80000)),
        "timeout_seconds": int(ingest.get("llm_timeout_seconds", 180)),
        "temperature": float(ingest.get("llm_temperature", 0.3)),
        "max_tokens": int(ingest.get("llm_max_tokens", 8192)),
    }


def format_transcript_for_llm(
    segments: list[dict[str, Any]],
    full_text: str,
    *,
    max_chars: int,
) -> str:
    if full_text and len(full_text) <= max_chars:
        return full_text

    lines: list[str] = []
    for seg in segments:
        start = float(seg.get("start") or 0)
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        mm = int(start // 60)
        ss = int(start % 60)
        lines.append(f"[{mm:02d}:{ss:02d}] {text}")

    body = "\n".join(lines) if lines else (full_text or "")
    if len(body) > max_chars:
        body = body[:max_chars] + "\n\n…（逐字稿过长，已截断供模型分析）"
    return body


def _format_user_payload(
    *,
    title: str,
    author: str,
    platform: str,
    source_url: str,
    sidecar_name: str,
    segments: list[dict[str, Any]],
    full_text: str,
    long_video: bool,
    max_chars: int,
) -> str:
    transcript = format_transcript_for_llm(segments, full_text, max_chars=max_chars)
    duration_min = 0.0
    if segments:
        last = segments[-1]
        duration_min = float(last.get("end") or last.get("start") or 0) / 60.0

    extra_title = ""
    if looks_like_placeholder_title(title):
        extra_title = (
            "\n\n**标题缺失**：请在输出最开头单独一行写 `建议标题：{不超过40字的中文标题}`，"
            "不要把它放进摘要里。"
        )

    return f"""请根据以下视频信息生成主笔记正文（Markdown，从 `## 摘要` 开始）。

# 元信息
- 标题：{title or "未命名"}
- 作者：{author or "未知"}
- 平台：{platform or "未知"}
- 链接：{source_url}
- 时长：约 {duration_min:.1f} 分钟
- 逐字稿文件：_transcripts/{sidecar_name}
- 视频类型：{"长视频" if long_video else "短视频"}{extra_title}

# 逐字稿
{transcript}

# 输出约束
1. 严格按系统提示中的章节顺序输出，使用 `## 章节名`。
2. **不要**输出 YAML frontmatter，**不要**输出 `# 一级标题`。
3. **不要**在正文重复粘贴完整逐字稿；`## 逐字稿` 只写一行链接：`[[_transcripts/{sidecar_name}]]`
"""


def chat_completion(*, system: str, user: str, settings: dict[str, Any]) -> str:
    if not settings.get("api_key"):
        raise RuntimeError("未配置 LLM_API_KEY（.env.local）")

    url = f"{settings['base_url']}/chat/completions"
    payload: dict[str, Any] = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings['api_key']}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=settings["timeout_seconds"]) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM 连接失败: {exc.reason}") from exc

    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"LLM 响应格式异常: {data}") from exc


def _parse_suggested_title(text: str) -> str | None:
    m = re.search(r"^建议标题[：:]\s*(.+)$", text, re.MULTILINE)
    if not m:
        return None
    title = m.group(1).strip().strip("\"'「」")
    return title[:80] if title else None


def _parse_sections(markdown: str, long_video: bool) -> dict[str, str]:
    order = SECTION_ORDER_LONG if long_video else SECTION_ORDER_SHORT
    sections: dict[str, str] = {}
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))
    if not matches:
        return sections

    for i, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        content = markdown[start:end].strip()
        if name in order or name.replace(" ", "") in [s.replace(" ", "") for s in order]:
            sections[name] = content

    return sections


def run_value_extraction(
    *,
    config: dict[str, Any],
    prompt_path: Path,
    title: str,
    author: str,
    platform: str,
    source_url: str,
    sidecar_name: str,
    segments: list[dict[str, Any]],
    full_text: str,
    long_video: bool,
) -> ValueExtractionResult:
    settings = llm_settings(config)
    if not settings["enabled"]:
        raise RuntimeError("LLM 未启用或未配置 API Key")

    system = prompt_path.read_text(encoding="utf-8")
    user = _format_user_payload(
        title=title,
        author=author,
        platform=platform,
        source_url=source_url,
        sidecar_name=sidecar_name,
        segments=segments,
        full_text=full_text,
        long_video=long_video,
        max_chars=settings["max_transcript_chars"],
    )

    raw = chat_completion(system=system, user=user, settings=settings)
    suggested = _parse_suggested_title(raw)
    sections = _parse_sections(raw, long_video)
    if not sections:
        raise RuntimeError("LLM 未返回可解析的 Markdown 章节")

    return ValueExtractionResult(
        suggested_title=suggested,
        sections=sections,
        raw_markdown=raw,
        long_video=long_video,
    )


def value_rating_from_section(text: str) -> str:
    for label in ("长期参考", "可二创", "仅存档", "不建议入库"):
        if label in text:
            return label
    return "仅存档"


def tags_from_keywords(keywords: str) -> str:
    bullets = re.findall(r"^[-*]\s*(.+)$", keywords, re.MULTILINE)
    if bullets:
        cleaned = [p.strip() for p in bullets if p.strip()]
    else:
        cleaned = [p.strip() for p in re.split(r"[、,，/|]", keywords) if p.strip()]
    return ", ".join(cleaned)[:240]


def looks_like_placeholder_title(title: str) -> bool:
    t = (title or "").strip()
    if not t or t in ("未命名", "untitled"):
        return True
    low = t.lower()
    if "xiaohongshu video" in low or re.search(r"video\s*#", low):
        return True
    return False
