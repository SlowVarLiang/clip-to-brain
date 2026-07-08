#!/usr/bin/env python3
"""管理商业客户账户（独立 API Key / 额度 / 限流）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parser.accounts import AccountStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="video-parser 多租户账户管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    add_p = sub.add_parser("add", help="新增客户账户")
    add_p.add_argument("--name", required=True, help="客户名称")
    add_p.add_argument("--quota", type=int, default=0, help="每月转写次数，0=不限")
    add_p.add_argument("--rate", type=int, default=0, help="每分钟限流，0=用全局默认")
    add_p.add_argument("--note", default="", help="备注")

    sub.add_parser("list", help="列出所有账户")

    usage_p = sub.add_parser("usage", help="查看本月用量")
    usage_p.add_argument("account_id", nargs="?", help="账户 ID，省略则显示全部")

    disable_p = sub.add_parser("disable", help="禁用账户")
    disable_p.add_argument("account_id")

    enable_p = sub.add_parser("enable", help="启用账户")
    enable_p.add_argument("account_id")

    rotate_p = sub.add_parser("rotate", help="轮换 API Key（旧 Key 立即失效）")
    rotate_p.add_argument("account_id")

    update_p = sub.add_parser("update", help="更新账户配置")
    update_p.add_argument("account_id")
    update_p.add_argument("--name")
    update_p.add_argument("--quota", type=int)
    update_p.add_argument("--rate", type=int)
    update_p.add_argument("--note")

    args = parser.parse_args()
    store = AccountStore()

    if args.cmd == "add":
        acc, api_key = store.add_account(
            args.name,
            rate_limit_per_minute=args.rate,
            monthly_quota=args.quota,
            note=args.note,
        )
        print("账户已创建（API Key 仅显示一次，请妥善保存）：")
        print(f"  id:      {acc.id}")
        print(f"  name:    {acc.name}")
        print(f"  api_key: {api_key}")
        print(f"  quota:   {acc.monthly_quota or '不限'}/月")
        print(f"  rate:    {acc.rate_limit_per_minute or '全局默认'}/分钟")
        return 0

    if args.cmd == "list":
        rows = store.list_accounts()
        if not rows:
            print("暂无账户。使用 add 创建，或继续用 .env 中的 API_KEY。")
            return 0
        for acc in rows:
            info = acc.public_info()
            status = "启用" if acc.enabled else "禁用"
            print(
                f"{info['id']}\t{info['name']}\t{status}\t"
                f"本月 {info['usage_this_month']}/{info['monthly_quota'] or '∞'}\t"
                f"限流 {info['rate_limit_per_minute'] or '默认'}/分钟"
            )
        return 0

    if args.cmd == "usage":
        if args.account_id:
            acc = store.get_account(args.account_id)
            if not acc:
                print(f"未找到账户: {args.account_id}", file=sys.stderr)
                return 1
            info = acc.public_info()
            print(json_line(info))
            return 0
        for acc in store.list_accounts():
            print(json_line(acc.public_info()))
        return 0

    if args.cmd == "disable":
        store.set_enabled(args.account_id, False)
        print(f"已禁用 {args.account_id}")
        return 0

    if args.cmd == "enable":
        store.set_enabled(args.account_id, True)
        print(f"已启用 {args.account_id}")
        return 0

    if args.cmd == "rotate":
        acc, api_key = store.rotate_key(args.account_id)
        print(f"已轮换 {acc.id} ({acc.name})，新 Key（仅显示一次）：")
        print(api_key)
        return 0

    if args.cmd == "update":
        store.update_account(
            args.account_id,
            name=args.name,
            rate_limit_per_minute=args.rate,
            monthly_quota=args.quota,
            note=args.note,
        )
        print(f"已更新 {args.account_id}")
        return 0

    return 1


def json_line(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
