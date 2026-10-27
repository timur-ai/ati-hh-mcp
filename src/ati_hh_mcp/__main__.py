"""CLI: запуск MCP-сервера (stdio и HTTP, этап M7).

HTTP-режим: streamable-http (uvicorn внутри FastMCP), дефолты
``--host 0.0.0.0 --port 8080``; маршруты ``/health`` и ``/oauth/callback``
регистрируются ``server.build_http_server``, гейт ``MCP_API_KEYS`` –
``server.RequestAuthMiddleware``. Защита от случайного открытия: HTTP-сервер
без MCP_API_KEYS на адресе вне loopback не запускается (exit code 2) –
задайте ключи или используйте ``--host 127.0.0.1`` для личного запуска.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from starlette.middleware import Middleware

from . import __version__
from .config import Config
from .server import RequestAuthMiddleware, build_http_server, build_server

#: Адреса, на которых открытый HTTP-режим допустим (личный запуск).
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_loopback(host: str) -> bool:
    """Является ли хост loopback-адресом (регистр и [::1]-скобки не важны)."""
    return host.strip().lower().strip("[]") in LOOPBACK_HOSTS


def _open_http_error(host: str) -> str:
    """Русское сообщение отказа старта открытого HTTP на внешнем адресе."""
    return (
        "Отказ запуска: HTTP-сервер без MCP_API_KEYS на адресе "
        f"{host} доступен из сети без авторизации. Задайте MCP_API_KEYS "
        "(список API-ключей через запятую) либо запустите с "
        "--host 127.0.0.1 для личного использования."
    )


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
    serve.add_argument("--host", default="0.0.0.0", help="HTTP listen host (default 0.0.0.0)")
    serve.add_argument("--port", type=int, default=8080, help="HTTP listen port (default 8080)")
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
        if not config.api_keys and not _is_loopback(args.host):
            print(_open_http_error(args.host), file=sys.stderr)
            return 2
        server = build_http_server(config)
        middleware = [Middleware(RequestAuthMiddleware, api_keys=config.api_keys)]
        asyncio.run(
            server.run_http_async(
                host=args.host,
                port=args.port,
                middleware=middleware,
                show_banner=False,
            )
        )
        return 0

    server = build_server(config)
    asyncio.run(server.run_async(transport="stdio", show_banner=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
