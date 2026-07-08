#!/usr/bin/env python3
import json
import re
import sys
from html import unescape
from pathlib import Path

import requests

url = sys.argv[1]
out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
r = requests.get(url, headers=headers, timeout=30)
text = r.text
title = ""
for pat in [
    r'var msg_title = "([^"]+)"',
    r"var msg_title = '([^']+)'",
    r'property="og:title" content="([^"]+)"',
    r'id="activity-name"[^>]*>([^<]+)<',
]:
    m = re.search(pat, text)
    if m:
        title = unescape(m.group(1).strip())
        break
author = ""
for pat in [r'var nickname = "([^"]+)"', r'id="js_name"[^>]*>([^<]+)<']:
    m = re.search(pat, text)
    if m:
        author = unescape(m.group(1).strip())
        break
content = ""
m = re.search(r'id="js_content"[^>]*>(.*)</div>\s*<script', text, re.S)
if m:
    raw = m.group(1)
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    raw = re.sub(r"</p>", "\n\n", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", "", raw)
    content = unescape(re.sub(r"\n{3,}", "\n\n", raw).strip())

result = {
    "success": bool(content),
    "source_url": url,
    "title": title,
    "author": author,
    "content": content,
    "content_len": len(content),
}
if out:
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
else:
    print(json.dumps(result, ensure_ascii=False, indent=2))
