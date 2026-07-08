"""飞书 / Telegram 丢链 Bot — 消息 → clip → 回执。"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+")


def extract_input_from_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^(归档|clip|入库|丢链|/clip)\s+", "", text, flags=re.I)
    urls = URL_IN_TEXT.findall(text)
    if urls:
        return urls[0]
    return text


def format_receipt(result: dict[str, Any], account_label: str = "予野") -> str:
    if not result.get("success"):
        lines = ["❌ 归档失败"]
        if result.get("error"):
            lines.append(f"原因：{result['error']}")
        if result.get("next_step"):
            lines.append(f"下一步：{result['next_step']}")
        return "\n".join(lines)

    lines = ["✅ 已入库"]
    if result.get("relative_path"):
        lines.append(f"📁 {result['relative_path']}")
    if result.get("title"):
        meta = " · ".join(x for x in (result.get("platform"), result.get("author")) if x)
        lines.append(f"📄 {result['title']}" + (f"（{meta}）" if meta else ""))
    if result.get("value_rating"):
        lines.append(f"⭐ {result['value_rating']}")
    angles = result.get("remix_angles") or []
    if angles:
        lines.append(f"💡 {account_label}可写：")
        for a in angles[:3]:
            lines.append(f"  · {a}")
    if result.get("topic_path"):
        lines.append(f"📝 选题卡：{result['topic_path']}")
    return "\n".join(lines)


def parse_feishu_event(body: dict[str, Any]) -> tuple[str, str] | None:
    """返回 (message_id, raw_text)。"""
    if body.get("type") == "url_verification":
        return None

    header = body.get("header") or {}
    if header.get("event_type") != "im.message.receive_v1":
        return None

    event = body.get("event") or {}
    message = event.get("message") or {}
    if message.get("message_type") != "text":
        return None

    message_id = message.get("message_id") or ""
    try:
        content = json.loads(message.get("content") or "{}")
        text = content.get("text") or ""
    except json.JSONDecodeError:
        text = message.get("content") or ""

    text = re.sub(r"@_\S+\s*", "", text).strip()
    if not text:
        return None
    return message_id, text


def feishu_url_verification_challenge(body: dict[str, Any]) -> dict[str, str] | None:
    if body.get("type") == "url_verification" and body.get("challenge"):
        return {"challenge": body["challenge"]}
    header = body.get("header") or {}
    if header.get("event_type") == "url_verification" and body.get("challenge"):
        return {"challenge": body["challenge"]}
    return None


def feishu_reply(message_id: str, text: str) -> None:
    token = _feishu_tenant_token()
    if not token or not message_id:
        return
    url = "https://open.feishu.cn/open-apis/im/v1/messages/" + message_id + "/reply"
    payload = {"msg_type": "text", "content": json.dumps({"text": text[:4000]}, ensure_ascii=False)}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def _feishu_tenant_token() -> str:
    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return ""

    cache_key = "_feishu_token_cache"
    cached = getattr(_feishu_tenant_token, cache_key, None)
    if cached:
        return cached

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    token = data.get("tenant_access_token") or ""
    setattr(_feishu_tenant_token, cache_key, token)
    return token


def parse_telegram_update(body: dict[str, Any]) -> tuple[str, str] | None:
    message = body.get("message") or body.get("edited_message")
    if not message:
        return None
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    text = message.get("text") or message.get("caption") or ""
    if not chat_id or not text.strip():
        return None
    return chat_id, text.strip()


def telegram_reply(chat_id: str, text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text[:4000]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def run_clip_async(
    raw_input: str,
    *,
    on_done: Any,
    profile: str | None = None,
    account: str | None = None,
) -> None:
    def worker() -> None:
        try:
            import sys
            from pathlib import Path

            scripts = Path(__file__).resolve().parent
            if str(scripts) not in sys.path:
                sys.path.insert(0, str(scripts))
            from content_archiver import load_config
            from clip import clip, result_to_dict

            config = load_config(scripts.parent / "config.json")
            from profile_loader import load_profile, default_profile_name

            pid = profile or account or os.getenv("CLIP_PROFILE") or default_profile_name(config)
            prof = load_profile(pid, config)
            result = clip.clip(raw_input, config, profile_id=prof.id, create_topic=True)
            payload = result_to_dict(result)
            payload["profile_label"] = prof.label
        except Exception as exc:
            payload = {"success": False, "error": str(exc)}
        try:
            on_done(payload)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def handle_feishu_event(body: dict[str, Any], *, profile: str | None = None) -> dict[str, Any]:
    challenge = feishu_url_verification_challenge(body)
    if challenge:
        return challenge

    parsed = parse_feishu_event(body)
    if not parsed:
        return {"ok": True, "ignored": True}

    message_id, text = parsed
    raw = extract_input_from_text(text)
    if not raw:
        feishu_reply(message_id, "请发送链接或正文（≥80字）")
        return {"ok": True}

    feishu_reply(message_id, "📥 已收到，解析/转写/萃取中…")

    def on_done(result: dict[str, Any]) -> None:
        label = result.get("profile_label") or "创作者"
        feishu_reply(message_id, format_receipt(result, label))

    run_clip_async(raw, on_done=on_done, profile=profile)
    return {"ok": True, "queued": True}


def handle_telegram_update(body: dict[str, Any], *, profile: str | None = None) -> dict[str, Any]:
    parsed = parse_telegram_update(body)
    if not parsed:
        return {"ok": True, "ignored": True}

    chat_id, text = parsed
    if text.startswith("/start"):
        telegram_reply(
            chat_id,
            "丢链即笔记\n\n"
            "· 直接发链接 → 归档到 Obsidian\n"
            "· 发长文（≥80字）→ 结构化笔记\n"
            "· /stats → 今日归档统计",
        )
        return {"ok": True}

    if text.strip() == "/stats":
        try:
            import sys
            from pathlib import Path

            scripts = Path(__file__).resolve().parent
            if str(scripts) not in sys.path:
                sys.path.insert(0, str(scripts))
            from clip_stats import collect_stats
            from content_archiver import load_config

            config = load_config(scripts.parent / "config.json")
            raw = config.get("YuYe_root") or config.get("lumis_root", "../vault")
            root = Path(raw)
            if not root.is_absolute():
                root = (scripts.parent / root).resolve()
            data = collect_stats(root, days=1)
            s = data["summary"]
            telegram_reply(
                chat_id,
                f"📊 今日归档 {s['today_total']} 条\n"
                f"可二创 {s['today_remixable']} · 长期参考 {s['today_long_ref']}",
            )
        except Exception as exc:
            telegram_reply(chat_id, f"统计失败：{exc}")
        return {"ok": True}

    raw = extract_input_from_text(text)
    if not raw:
        telegram_reply(chat_id, "请发送 http 链接或 ≥80 字正文")
        return {"ok": True}

    telegram_reply(chat_id, "📥 处理中…")

    def on_done(result: dict[str, Any]) -> None:
        label = result.get("profile_label") or "创作者"
        telegram_reply(chat_id, format_receipt(result, label))

    run_clip_async(raw, on_done=on_done, profile=profile)
    return {"ok": True, "queued": True}


def telegram_get_updates(token: str, *, offset: int = 0, timeout: int = 30) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "timeout": str(timeout),
        "allowed_updates": '["message","edited_message"]',
    }
    if offset:
        params["offset"] = str(offset)
    url = f"https://api.telegram.org/bot{token}/getUpdates?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "getUpdates 失败"))
    return data.get("result") or []


def run_telegram_poll(*, profile: str | None = None) -> None:
    import time

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("请设置 TELEGRAM_BOT_TOKEN")

    offset = 0
    print("Telegram 长轮询已启动（Ctrl+C 退出）", flush=True)
    while True:
        try:
            updates = telegram_get_updates(token, offset=offset, timeout=30)
            for upd in updates:
                offset = int(upd.get("update_id", 0)) + 1
                handle_telegram_update(upd, profile=profile or os.getenv("CLIP_PROFILE", "default-creator"))
        except KeyboardInterrupt:
            print("\n已停止")
            break
        except Exception as exc:
            print(f"轮询错误: {exc}", flush=True)
            time.sleep(5)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Clip-to-Brain Bot")
    parser.add_argument("command", choices=["poll"], nargs="?", default="poll")
    parser.add_argument("--profile", default=os.getenv("CLIP_PROFILE", "default-creator"))
    args = parser.parse_args()

    if args.command == "poll":
        run_telegram_poll(profile=args.profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
