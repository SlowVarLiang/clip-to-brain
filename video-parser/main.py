#!/usr/bin/env python3
"""
视频去水印解析工具 — 支持 80+ 平台

用法:
  python main.py                          # 交互模式，粘贴链接自动解析
  python main.py "https://v.douyin.com/xxx"
  python main.py --download "链接"
  python main.py --serve                  # 启动 HTTP API
  python main.py --platforms              # 列出支持的平台
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

console = Console()


def print_result(result) -> None:
    if result.success:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[green]✓ 解析成功[/green]")
        table.add_row("平台", f"[cyan]{result.platform}[/cyan]")
        table.add_row("引擎", result.backend)
        if result.title:
            table.add_row("标题", result.title)
        if result.author:
            table.add_row("作者", result.author)
        if result.video_url:
            table.add_row("视频", result.video_url[:120] + ("..." if len(result.video_url) > 120 else ""))
        if result.music_url:
            table.add_row("音乐", result.music_url[:120])
        if result.images:
            table.add_row("图集", f"{len(result.images)} 张")
            for i, img in enumerate(result.images[:3]):
                table.add_row(f"  图{i + 1}", img[:100])
            if len(result.images) > 3:
                table.add_row("", f"... 共 {len(result.images)} 张")
        console.print(Panel(table, title="解析结果", border_style="green"))
    else:
        console.print(Panel(f"[red]✗ 解析失败[/red]\n{result.error}", title=result.platform, border_style="red"))


async def cmd_parse(text: str, download: bool, output_dir: str, fmt: str) -> int:
    from parser.unified import parse_text

    results = await parse_text(text)
    exit_code = 0

    for result in results:
        if fmt == "json":
            console.print_json(json.dumps(result.to_dict(), ensure_ascii=False))
        else:
            print_result(result)

        if download and result.success:
            from parser.download import download_result

            try:
                paths = await download_result(result, output_dir)
                console.print(f"[green]已下载 {len(paths)} 个文件到 {output_dir}[/green]")
                for p in paths:
                    console.print(f"  → {p}")
            except Exception as exc:
                console.print(f"[red]下载失败: {exc}[/red]")
                exit_code = 1

        if not result.success:
            exit_code = 1

    return exit_code


def cmd_platforms() -> None:
    from parser.platforms import PLATFORMS

    table = Table(title="支持的平台")
    table.add_column("平台", style="cyan")
    table.add_column("解析引擎", style="yellow")
    table.add_column("域名示例", style="dim")

    for p in PLATFORMS:
        table.add_row(p.name, p.backend, ", ".join(p.domains[:2]))

    console.print(table)
    console.print(f"\n共 [bold]{len(PLATFORMS)}[/bold] 个平台。未列出的链接会尝试 yt-dlp 通用解析（1800+ 站点）。")


async def interactive_loop(download: bool, output_dir: str) -> None:
    console.print(
        Panel(
            "[bold]视频去水印解析工具[/bold]\n"
            "直接粘贴分享链接或整段文案，回车解析\n"
            "输入 [cyan]q[/cyan] 退出  |  [cyan]list[/cyan] 查看平台",
            border_style="blue",
        )
    )

    while True:
        try:
            text = console.input("\n[bold blue]链接>[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n再见!")
            break

        if not text:
            continue
        if text.lower() in ("q", "quit", "exit"):
            console.print("再见!")
            break
        if text.lower() in ("list", "platforms", "平台"):
            cmd_platforms()
            continue

        await cmd_parse(text, download, output_dir, "text")


def main() -> None:
    parser = argparse.ArgumentParser(description="视频去水印解析 — 80+ 平台")
    parser.add_argument("url", nargs="?", help="视频/图集分享链接或含链接的文案")
    parser.add_argument("-d", "--download", action="store_true", help="解析后下载到本地")
    parser.add_argument("-o", "--output", default="./downloads", help="下载目录 (默认 ./downloads)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--serve", action="store_true", help="启动 HTTP API 服务")
    parser.add_argument("--platforms", action="store_true", help="列出支持的平台")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互模式")

    args = parser.parse_args()

    if args.platforms:
        cmd_platforms()
        return

    if args.serve:
        from parser.server import run_server

        console.print("[green]启动 API 服务...[/green]")
        console.print("  Web UI  http://localhost:8765/")
        console.print("  GET  /parse?url=链接")
        console.print("  POST /parse  (form: url 或 text)")
        console.print("  POST /transcribe  (json: video_url)")
        run_server()
        return

    if args.interactive or not args.url:
        asyncio.run(interactive_loop(args.download, args.output))
        return

    fmt = "json" if args.json else "text"
    code = asyncio.run(cmd_parse(args.url, args.download, args.output, fmt))
    sys.exit(code)


if __name__ == "__main__":
    main()
