"""予野六页 · GPT Image 2 风格与 prompt 拼装。

换选题只改 pages.json 的 content；风格由 pages.json 顶层 theme 切换。
"""
from __future__ import annotations

THEMES: dict[str, dict[str, str]] = {
    "data-white": {
        "prefix": (
            "小红书竖版信息图卡片，1080x1440，3:4比例，"
            "白底数据风 infographic，米白背景 #FAFAF8，"
            "藏青色标题 #1A3352，橙红色强调 #EF4822，"
            "3px 粗黑圆角边框，轻阴影，左上小点阵装饰，"
            "杂志级排版，扁平矢量插画风，充满高级感。"
        ),
        "negative": (
            "低质量，模糊，噪点，畸形，乱码文字，英文乱入，水印，logo，"
            "3D写实，电影感，游艇，霸总，过度装饰，"
            "渐变滥用，霓虹，赛博朋克，多面板拼贴，"
            "人物照片，真实人脸，IP，卡通人物，复杂背景，拥挤排版。"
        ),
        "no_figure": "无人物，无IP，纯信息图。",
    },
    "dark-red-tech": {
        "prefix": (
            "小红书竖版信息图，1080x1440，3:4，"
            "暗黑科技风 tech-noir cyber infographic，纯黑底 #0A0A0A，"
            "叠加数字网格HUD线框、微弱城市虚化、红色地面反光，"
            "霓虹红高光 #FF2D2D 光晕 lens flare，白色粗体标题与红色关键词混排，"
            "左上超大白色章节序号，右上红色pill分类标签，"
            "中部主视觉带发光portal/3D科技图标/立体流程图/数据面板，"
            "底部白色细线描边图标行+CTA，信息层次丰富，"
            "高对比红黑白，AI工具商业科技感，非简约flat，细节充实。"
        ),
        "negative": (
            "低质量，模糊，乱码，白底，米白，极简，性冷淡风，大量留白，"
            "扁平手册风，水印，logo，人物照片，真实人脸，IP，"
            "过度杂乱不可读，游艇，霸总。"
        ),
        "no_figure": "无人物，无IP，无真实人脸。",
    },
}

_current_theme = "data-white"


def set_theme(name: str) -> None:
    global _current_theme
    _current_theme = name if name in THEMES else "data-white"


def get_theme() -> str:
    return _current_theme


def _t() -> dict[str, str]:
    return THEMES[_current_theme]


def build_prompt(page: dict) -> str:
    if "prompt" in page and "content" not in page:
        return page["prompt"]
    c = page.get("content") or {}
    ptype = page.get("type") or c.get("type", "inner")
    if ptype == "cover":
        return _cover(c)
    if ptype == "table":
        return _table(c)
    if ptype == "case":
        return _case(c)
    if ptype == "cta":
        return _cta(c)
    return _inner(c)


def _cover(c: dict) -> str:
    lines = c.get("title_lines") or []
    title_block = "、".join(f"「{t}」" for t in lines)
    subtitle = c.get("subtitle", "")
    visual = c.get("visual", "")
    footer = c.get("footer", "予野YuYe · 1/6")
    chapter = c.get("chapter", "01")
    pill = c.get("pill", "工具亲测")
    t = _t()
    if _current_theme == "dark-red-tech":
        return (
            t["prefix"]
            + "封面 layout："
            f"左上超大白色序号「{chapter}」，右上红色pill标签「{pill}」，"
            f"主标题{len(lines)}行白红混排超大粗体{title_block}，"
            f"白色副标题「{subtitle}」，"
            f"中部主视觉{visual}，带红色光晕和HUD装饰，"
            "底部白色图标行+收藏引导，"
            f"左下角小字「{footer}」，"
            f"{t['no_figure']}"
            + t["negative"]
        )
    return (
        t["prefix"]
        + "封面页 layout："
        f"上半区居中超大藏青粗体标题{len(lines)}行{title_block}，"
        f"下方居中橙红色副标题「{subtitle}」+ 短橙线，"
        f"下半区{visual}，"
        f"对称平衡，信息充实，{t['no_figure']}"
        f"底部细灰线，左下角页脚「{footer}」。"
        + t["negative"]
    )


def _inner(c: dict) -> str:
    tag = c.get("tag", "")
    bullets = c.get("bullets") or []
    extra = c.get("extra", "")
    bullet_text = "。".join(bullets) if bullets else c.get("body", "")
    chapter = c.get("chapter", "")
    t = _t()
    if _current_theme == "dark-red-tech":
        ch = f"左上超大白序号「{chapter}」，" if chapter else ""
        return (
            t["prefix"]
            + "内页 layout："
            f"{ch}右上红色pill「{tag}」，"
            f"主体为{len(bullets) or '多'}条信息，每条在暗色半透明面板内，红色左边框高亮，白字正文，"
            f"内容完整呈现：{bullet_text}。"
            f"{extra}"
            "背景HUD网格，红色微光，信息密度高，无页码，"
            f"{t['no_figure']}"
            + t["negative"]
        )
    return (
        t["prefix"]
        + "内页 layout："
        f"左上橙红实心圆角标签「{tag}」白字，"
        f"主体为{len(bullets) or '多'}条左对齐列表，每条前橙红圆点，藏青正文，"
        f"内容必须完整呈现：{bullet_text}。"
        f"{extra}"
        f"大行距但信息饱满，底部虚线分割，无页码，{t['no_figure']}"
        + t["negative"]
    )


def _table(c: dict) -> str:
    tag = c.get("tag", "对比表")
    headers = c.get("headers") or ["A", "B"]
    rows = c.get("rows") or []
    row_desc = "；".join(
        f"{r.get('label', '')}（{r.get('left', '')} vs {r.get('right', '')}）" for r in rows
    )
    chapter = c.get("chapter", "")
    t = _t()
    if _current_theme == "dark-red-tech":
        ch = f"左上白序号「{chapter}」，" if chapter else ""
        return (
            t["prefix"]
            + "内页 layout："
            f"{ch}右上红pill「{tag}」，"
            f"中部发光表格，表头霓虹红底白字，左列{headers[0]}右列{headers[1]}，"
            f"共{len(rows)}行：{row_desc}，"
            "暗色网格线+红色分割线，HUD背景，高信息密度收藏向，无页码，"
            f"{t['no_figure']}"
            + t["negative"]
        )
    return (
        t["prefix"]
        + "内页 layout："
        f"左上橙标「{tag}」，"
        f"中部清晰两列表格，表头左{headers[0]}右{headers[1]}藏青底白字，"
        f"共{len(rows)}行数据：{row_desc}，"
        "橙红分割线，网格线清晰，每格文字完整可读，高信息密度收藏向，无页码，"
        f"{t['no_figure']}"
        + t["negative"]
    )


def _case(c: dict) -> str:
    tag = c.get("tag", "")
    cases = c.get("cases") or []
    case_text = "；".join(
        f"坑{i+1}：{x.get('scene', '')}（{x.get('detail', '')}）"
        for i, x in enumerate(cases)
    )
    chapter = c.get("chapter", "")
    t = _t()
    if _current_theme == "dark-red-tech":
        ch = f"左上白序号「{chapter}」，" if chapter else ""
        return (
            t["prefix"]
            + "内页 layout："
            f"{ch}右上红pill「{tag}」，"
            f"{len(cases)}张暗色卡片竖排，每卡红色警示图标+白字，"
            f"完整内容：{case_text}，"
            "卡片间红色细线，红色光晕边缘，踩坑警示感，无页码，"
            f"{t['no_figure']}"
            + t["negative"]
        )
    return (
        t["prefix"]
        + "内页 layout："
        f"左上橙标「{tag}」，"
        f"{len(cases)}个场景卡片竖排，每卡片左侧小线框图标右侧藏青中文，"
        f"完整内容：{case_text}，"
        "卡片间细灰线分隔，亲测实用感，信息密度高，无页码，"
        f"{t['no_figure']}"
        + t["negative"]
    )


def _cta(c: dict) -> str:
    title = c.get("title", "")
    hook = c.get("hook", "")
    signature = c.get("signature", "慢慢来，才更快")
    extras = c.get("extras") or []
    extra_text = "。".join(extras)
    chapter = c.get("chapter", "06")
    t = _t()
    if _current_theme == "dark-red-tech":
        return (
            t["prefix"]
            + "CTA转化页 layout："
            f"左上白序号「{chapter}」，"
            f"居中超大白红混排标题「{title}」，"
            f"霓虹红引导语「{hook}」，"
            "红色发光向下箭头+书签收藏图标，"
            f"{'底部：' + extra_text + '。' if extra_text else ''}"
            f"左下白色签名「{signature}」，"
            "红色portal光效背景，无页码，无下篇预告，"
            f"{t['no_figure']}"
            + t["negative"]
        )
    return (
        t["prefix"]
        + "CTA转化页 layout："
        f"居中藏青大标题「{title}」，"
        f"橙红引导语「{hook}」，"
        "向下橙色箭头+书签收藏图标，"
        f"{'还有：' + extra_text + '。' if extra_text else ''}"
        f"{t['no_figure']}"
        + t["negative"]
    )


# 向后兼容 generate 脚本默认 PAGES
STYLE_PREFIX = THEMES["data-white"]["prefix"]
STYLE_NEGATIVE = THEMES["data-white"]["negative"]
NO_FIGURE = THEMES["data-white"]["no_figure"]
