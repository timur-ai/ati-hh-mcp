# Development

The project uses [uv](https://docs.astral.sh/uv/) exclusively; Python 3.10 –
3.14 is supported (the CI matrix runs every minor version).

```bash
git clone https://github.com/timur-ai/ati-hh-mcp
cd ati-hh-mcp
uv sync --dev          # environment with dev dependencies
```

## Checks

```bash
uv run pytest -q             # unit + contract + MCP client e2e
uv run ruff check src tests  # lint
uv run mypy src              # strict type checking
uv run coverage report       # line coverage of src/
```

Live integration tests (`tests/integration_live/`, marker `live`) are opt-in
and read-only; they take the hh.ru token from the `HH_LIVE_TOKEN` secret and
mask it in logs.

```bash
uv run pytest -m live --live-token  # see tests/integration_live/ for options
```

## Repository map

| Path | Purpose |
| --- | --- |
| `src/ati_hh_mcp/toolsets/` | one module per toolset; each tool declared via `toolkit.make_tool` |
| `src/ati_hh_mcp/registry.py` | tool ↔ OpenAPI operation registry (metatest source of truth) |
| `src/ati_hh_mcp/hh/` | HTTP client, OAuth, SQLite token store, structured errors |
| `tests/contract/` | coverage metatest + schema validation against live fixtures |
| `docs/openapi/hh-openapi.yaml` | vendored hh.ru OpenAPI specification (canon) |
| `docs/fixtures/` | live-recorded, sanitized responses for contract tests |
| `docs/tools/` | generated tool reference (do not edit) |

## Maintenance scripts

```bash
bash scripts/fetch_openapi.sh               # refresh the vendored OpenAPI spec
uv run python scripts/record_fixtures.py    # re-record live fixtures (read-only, sanitized)
uv run python scripts/gen_tool_docs.py      # regenerate docs/tools/ from the registry
uv run mkdocs serve                         # docs site at http://127.0.0.1:8000
```

After changing a toolset, regenerate the tool reference and rebuild the docs:

```bash
uv run python scripts/gen_tool_docs.py && uv run mkdocs build --strict
```

## Adding a toolset

1. Create `src/ati_hh_mcp/toolsets/<name>.py` with `TOOLSET_NAME` and
   `register(mcp, client_factory)`, declaring each tool through
   `make_tool(operation_id=..., ...)` – the operation id must match the
   vendored specification.
2. Add `tests/contract/groups_<name>.py` (`TOOLSET`, `OPERATIONS`) – the
   coverage metatest picks it up automatically and locks the parametric
   contract.
3. Wire the module in `src/ati_hh_mcp/server.py` (`TOOLSET_MODULES`), add
   unit tests, regenerate `docs/tools/`.

## Design records

- [ADR Z1: FastMCP major choice](adr/Z1-fastmcp-major.md)
