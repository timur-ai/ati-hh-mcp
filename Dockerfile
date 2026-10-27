# Сборка: uv создаёт изолированный venv без dev-зависимостей.
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
# Сначала только манифесты – слой зависимостей кешируется отдельно от кода.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY README.md LICENSE ./
RUN uv sync --locked --no-dev

# Рантайм: только venv и исходники, непривилегированный пользователь.
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HH_TOKEN_STORE=/data/tokens.sqlite3
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data /app
USER appuser
EXPOSE 8080
# Проверка живости без curl: системный python + urllib (зависимости не нужны).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"]
ENTRYPOINT ["ati-hh-mcp", "serve", "--transport", "http", "--host", "0.0.0.0", "--port", "8080"]
