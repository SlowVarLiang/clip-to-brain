"""逐字稿处理：长短视频分流、章节抽样、启发式萃取。"""

from __future__ import annotations

import re
from typing import Any

_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("教程方法论", ("教程", "入门", "学会", "保姆", "步骤", "如何", "手把手", "功能", "配置", "SOP")),
    ("案例拆解", ("拆解", "复盘", "案例", "对标", "分析")),
    ("行业观察", ("行业", "趋势", "市场", "报告", "观察")),
    ("观点输出", ("我认为", "观点", "为什么", "真相", "本质")),
    ("个人经验", ("我的经验", "踩坑", "亲身经历")),
    ("情绪表达", ("焦虑", "崩溃", "太卷了")),
]

_QUOTE_HINTS = ("才是", "真正", "关键", "不要", "必须", "其实", "就是", "最好", "唯一", "秘诀", "核心")

_ACTION_HINTS = (
    "首先", "然后", "步骤", "打开", "点击", "设置", "安装", "推荐", "选择", "新建",
    "配置", "下载", "登录", "启用", "关闭", "输入", "调用", "创建",
)

_KNOWN_TOOLS = (
    "Codex", "ChatGPT", "Claude", "Claude Code", "GPT", "Whisper", "Obsidian",
    "Notion", "Figma", "Canva", "Gmail", "GitHub", "Remotion", "Cursor",
    "agents.md", "Skills", "Computer Use", "Image", "Docker", "Vercel",
)

_BANNED_KW = frozenset(
    {"内容", "方法", "干货", "视频", "分享", "今天", "大家", "我们", "这个", "那个", "一个"}
)


def parse_timestamp(ts: str) -> float:
    ts = (ts or "0").strip().replace(",", ".")
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        return float(parts[0])
    except (ValueError, IndexError):
        return 0.0


def format_time_label(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def transcript_duration_seconds(segments: list[dict[str, Any]]) -> float:
    if not segments:
        return 0.0
    last = segments[-1]
    end = parse_timestamp(str(last.get("end_time") or last.get("begin_time") or "0"))
    return max(end, 0.0)


def is_long_video(
    segments: list[dict[str, Any]],
    full_text: str,
    *,
    min_minutes: float = 10.0,
    min_chars: int = 8000,
    min_segments: int = 200,
) -> bool:
    if len(segments) >= min_segments:
        return True
    if len(full_text or "") >= min_chars:
        return True
    return transcript_duration_seconds(segments) >= min_minutes * 60


def _split_sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[。！？；.!?;])\s*", text)
    return [p.strip() for p in parts if p.strip()]


def truncate_text(text: str, max_chars: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in ("。", "！", "？", ".", " "):
        idx = cut.rfind(sep)
        if idx > max_chars // 3:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


def summary_from_text(text: str, *, max_sentences: int = 3, max_chars: int = 420) -> str:
    text = (text or "").strip()
    if not text:
        return "（无逐字稿）"

    parts = _split_sentences(text)
    if len(parts) >= 2:
        return truncate_text("".join(parts[:max_sentences]), max_chars)

    if len(text) > max_chars:
        chunk = max(max_chars // max_sentences, 80)
        slices = [text[i : i + chunk] for i in range(0, min(len(text), chunk * max_sentences), chunk)]
        return truncate_text("".join(slices), max_chars)
    return text


def excerpt_time_window(
    segments: list[dict[str, Any]], start_sec: float, end_sec: float, max_segments: int = 12
) -> str:
    picked: list[str] = []
    for seg in segments:
        t = parse_timestamp(str(seg.get("begin_time", "0")))
        if start_sec <= t <= end_sec:
            txt = (seg.get("text") or "").strip()
            if txt:
                picked.append(txt)
        if len(picked) >= max_segments:
            break
    return "".join(picked)


def build_long_video_summary(segments: list[dict[str, Any]], full_text: str) -> str:
    dur = transcript_duration_seconds(segments)
    if dur <= 0:
        return summary_from_text(full_text)

    parts: list[str] = []
    for start, end in [
        (0, min(90, dur * 0.1)),
        (dur * 0.35, dur * 0.35 + 60),
        (max(0, dur - 75), dur),
    ]:
        ex = truncate_text(excerpt_time_window(segments, start, end, max_segments=8), 120)
        if ex:
            parts.append(ex.rstrip("。"))

    chapters = build_chapter_outline(segments, chapter_count=6)
    if chapters and len(parts) < 5:
        parts.append(chapters[len(chapters) // 2]["summary"].rstrip("。"))

    if not parts:
        return summary_from_text(full_text, max_sentences=4, max_chars=520)
    return "。".join(parts[:5]) + "。"


def build_chapter_outline(
    segments: list[dict[str, Any]], *, chapter_count: int = 6
) -> list[dict[str, str]]:
    if not segments:
        return []

    dur = transcript_duration_seconds(segments)
    if dur <= 0:
        return []

    chapter_count = max(3, min(chapter_count, 8))
    step = dur / chapter_count
    rows: list[dict[str, str]] = []

    for i in range(chapter_count):
        start = i * step
        end = (i + 1) * step if i < chapter_count - 1 else dur
        excerpt = excerpt_time_window(segments, start, end, max_segments=20)
        summary = truncate_text(excerpt, 100) or "—"
        topic = ""
        for seg in segments:
            t = parse_timestamp(str(seg.get("begin_time", "0")))
            if start <= t <= end:
                txt = (seg.get("text") or "").strip()
                if len(txt) >= 4:
                    topic = truncate_text(txt, 24)
                    break
        rows.append(
            {
                "time_range": f"{format_time_label(start)}-{format_time_label(end)}",
                "topic": topic or f"第{i + 1}段",
                "summary": summary,
            }
        )
    return rows


def format_chapter_table(chapters: list[dict[str, str]]) -> str:
    if not chapters:
        return "（无）"
    lines = ["| 时间段 | 章节主题 | 一句话概要 |", "|--------|----------|------------|"]
    for ch in chapters:
        lines.append(f"| {ch['time_range']} | {ch['topic']} | {ch['summary']} |")
    return "\n".join(lines)


def pick_golden_quotes(segments: list[dict[str, Any]], max_quotes: int = 4) -> list[str]:
    if not segments:
        return ["无"]

    dur = transcript_duration_seconds(segments) or 1.0
    buckets: list[list[tuple[int, int, str]]] = [[] for _ in range(max_quotes)]

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if len(text) < 10 or len(text) > 120:
            continue
        t = parse_timestamp(str(seg.get("begin_time", "0")))
        score = sum(1 for h in _QUOTE_HINTS if h in text)
        if score == 0 and len(text) < 18:
            continue
        idx = min(int(t / dur * max_quotes), max_quotes - 1)
        buckets[idx].append((score, len(text), text))

    quotes: list[str] = []
    seen: set[str] = set()
    for bucket in buckets:
        if not bucket:
            continue
        bucket.sort(key=lambda x: (-x[0], -x[1]))
        q = bucket[0][2]
        if q not in seen:
            seen.add(q)
            quotes.append(q)

    if len(quotes) < 2:
        step = max(len(segments) // max_quotes, 1)
        for i in range(0, len(segments), step):
            text = (segments[i].get("text") or "").strip()
            if 15 <= len(text) <= 100 and text not in seen:
                seen.add(text)
                quotes.append(text)
            if len(quotes) >= max_quotes:
                break

    return quotes[:max_quotes] if quotes else ["无"]


def core_points_heuristic(segments: list[dict[str, Any]], *, count: int = 3) -> list[str]:
    dur = transcript_duration_seconds(segments)
    if dur <= 0:
        return ["（无）"] * count

    n = max(1, count)
    step = dur / n
    points: list[str] = []
    for i in range(n):
        start = i * step
        end = (i + 1) * step if i < n - 1 else dur
        excerpt = truncate_text(excerpt_time_window(segments, start, end, max_segments=16), 180)
        if excerpt:
            label = format_time_label(start)
            points.append(f"（约 {label} 起）{excerpt}")

    while len(points) < count:
        points.append("（无）")
    return points[:count]


def extract_action_items(segments: list[dict[str, Any]], *, max_items: int = 8) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if len(text) < 8 or len(text) > 100:
            continue
        if not any(h in text for h in _ACTION_HINTS):
            continue
        if text in seen:
            continue
        seen.add(text)
        items.append(text)
        if len(items) >= max_items:
            break
    return items


def extract_tools_table(segments: list[dict[str, Any]], title: str = "") -> list[tuple[str, str]]:
    blob = title + " " + " ".join((s.get("text") or "") for s in segments[:400])
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tool in _KNOWN_TOOLS:
        if tool.lower() in blob.lower() or tool in blob:
            key = tool.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append((tool, "视频中提及"))
    for m in re.finditer(r"\b[A-Z][A-Za-z0-9+.]{2,}\b", blob):
        w = m.group(0)
        if w in ("GPT", "API", "URL", "PDF") or w.lower() in seen:
            continue
        if len(found) >= 12:
            break
        seen.add(w.lower())
        found.append((w, "视频中提及"))
    return found[:12]


def format_tools_table(tools: list[tuple[str, str]]) -> str:
    if not tools:
        return "（无）"
    lines = ["| 名称 | 用途/角色 |", "|------|-----------|"]
    for name, role in tools:
        lines.append(f"| {name} | {role} |")
    return "\n".join(lines)


def infer_keywords(
    title: str,
    author: str,
    platform: str,
    segments: list[dict[str, Any]],
    *,
    max_count: int = 8,
) -> str:
    kws: list[str] = []
    for token in re.split(r"[^\w\d\u4e00-\u9fff+#]+", title or ""):
        token = token.strip()
        if len(token) >= 2 and token not in _BANNED_KW:
            kws.append(token)
    if author:
        kws.append(author.strip())
    if platform and platform not in kws:
        kws.append(platform)

    freq: dict[str, int] = {}
    for seg in segments[:300]:
        for m in re.finditer(r"[A-Za-z][A-Za-z0-9._-]{2,}", seg.get("text") or ""):
            w = m.group(0)
            if w.lower() not in ("http", "https", "www", "com"):
                freq[w] = freq.get(w, 0) + 1
    for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:5]:
        kws.append(w)

    dedup: list[str] = []
    seen: set[str] = set()
    for k in kws:
        kl = k.lower()
        if kl not in seen and k not in _BANNED_KW:
            seen.add(kl)
            dedup.append(k)
    return "、".join(dedup[:max_count]) if dedup else "（无）"


def infer_keywords_long(
    title: str, author: str, platform: str, segments: list[dict[str, Any]]
) -> str:
    return infer_keywords(title, author, platform, segments, max_count=12)


def guess_content_category(title: str, sample_text: str) -> str:
    blob = f"{title} {sample_text[:2000]}"
    scores: dict[str, int] = {name: 0 for name, _ in _CATEGORY_RULES}
    for name, keys in _CATEGORY_RULES:
        for k in keys:
            if k in blob:
                scores[name] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "案例拆解"


def guess_value_rating(content_category: str, is_long: bool, transcript_ok: bool) -> tuple[str, str]:
    if not transcript_ok:
        return "仅存档", "**仅存档** — 无逐字稿，仅保留元数据。"
    if content_category == "教程方法论" and is_long:
        return "长期参考", "**长期参考** — 长教程结构完整，章节脉络与实操要点已拆解，适合反复查阅。"
    if content_category == "教程方法论":
        return "长期参考", "**长期参考** — 教程类，步骤清晰，具备复用价值。"
    if is_long:
        return "可二创", "**可二创** — 长内容信息量大，已拆章节与要点，适合二次创作与裁剪。"
    return "可二创", "**可二创** — 素材完整，适合作为灵感来源。"


def fmt_transcript_lines(segments: list[dict[str, Any]]) -> str:
    if not segments:
        return "（暂无逐字稿）"
    return "\n".join(
        f"- `[{s.get('begin_time', '?')} → {s.get('end_time', '?')}]` {s.get('text', '')}"
        for s in segments
    )


_SIDEcar_LINE = re.compile(
    r"^- `\[(?P<begin>[^\]]+?)\s*→\s*(?P<end>[^\]]+?)\]`\s*(?P<text>.*)$"
)


def _time_to_seconds(ts: str) -> float:
    ts = ts.strip().split(".")[0]
    parts = ts.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0.0


def read_transcript_sidecar(path: Path) -> tuple[list[dict[str, Any]], str, str]:
    """从 sidecar 文件解析分段、标题、来源 URL。"""
    text = path.read_text(encoding="utf-8")
    title = "未命名"
    source_url = ""
    m_title = re.search(r"^#\s*逐字稿[：:]\s*(.+)$", text, re.MULTILINE)
    if m_title:
        title = m_title.group(1).strip()
    m_src = re.search(r"^>\s*来源[：:]\s*(\S+)", text, re.MULTILINE)
    if m_src:
        source_url = m_src.group(1).strip()

    segments: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = _SIDEcar_LINE.match(line.strip())
        if not m:
            continue
        begin = m.group("begin").strip()
        end = m.group("end").strip()
        seg_text = m.group("text").strip()
        segments.append(
            {
                "begin_time": begin,
                "end_time": end,
                "start": _time_to_seconds(begin),
                "end": _time_to_seconds(end),
                "text": seg_text,
            }
        )
    return segments, title, source_url


def write_transcript_sidecar(path, segments: list[dict[str, Any]], *, title: str, source_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dur_min = transcript_duration_seconds(segments) / 60
    header = (
        f"# 逐字稿：{title}\n\n"
        f"> 来源：{source_url} · 约 {dur_min:.1f} 分钟 · {len(segments)} 段\n\n"
        "## 全文（带时间戳）\n\n"
    )
    path.write_text(header + fmt_transcript_lines(segments), encoding="utf-8")
