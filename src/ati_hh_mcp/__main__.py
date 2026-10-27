"""CLI: запуск MCP-сервера (stdio; HTTP – этап M7)."""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import __version__
from .config import Config
from .server import build_server


def build_parser() -> argparse.ArgumentParser:
    """Парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        prog="ati-hh-mcp",
        description="Public MCP server for the hh.ru API",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the MCP server")
    serve.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport: stdio (default) or http",
    )
    serve.add_argument("--host", default="127.0.0.1", help="HTTP listen host")
    serve.add_argument("--port", type=int, default=8000, help="HTTP listen port")
    serve.add_argument(
        "--toolsets",
        default=None,
        help="Comma-separated toolsets override (default: HH_TOOLSETS env)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Точка входа консольного скрипта."""
    args = build_parser().parse_args(argv)

    config = Config.from_env()
    if args.toolsets:
        names = tuple(p.strip() for p in args.toolsets.split(",") if p.strip())
        config = config.with_toolsets(names)

    if args.transport == "http":
        # Заглушка до этапа M7 (транспорты и Docker).
        print(
            "HTTP-транспорт будет реализован на этапе M7; пока доступен только "
            "stdio (--transport stdio).",
            file=sys.stderr,
        )
        return 2

    server = build_server(config)
    asyncio.run(server.run_async(transport="stdio", show_banner=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
