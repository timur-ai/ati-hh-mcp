# ati-hh-mcp

Public MCP (Model Context Protocol) server for the [hh.ru](https://hh.ru) API:
every operation of the public hh.ru OpenAPI specification – all 135 of them –
exposed as grouped, switchable toolsets for LLM agents. stdio for personal
use, streamable HTTP with API keys and OAuth for teams.

- **Complete and verified**: 135/135 public OpenAPI operations are implemented
  and locked by a contract metatest (operations *and* required parameters);
  responses are checked against the vendored specification with live-recorded
  fixtures.
- **Safe by design**: mutations require an explicit `confirm=true` argument;
  GET requests are throttled and retried on 429, mutations never repeat
  automatically; tokens never appear in logs.
- **Built for LLMs**: domain-prefixed snake_case tool names, concise English
  descriptions, structured errors with hh.ru codes and Russian descriptions.

The repository also ships a [Russian README](https://github.com/timur-ai/ati-hh-mcp/blob/main/README_RU.md).

## Quick start (stdio)

```bash
uvx --from git+https://github.com/timur-ai/ati-hh-mcp ati-hh-mcp serve --transport stdio
```

Point an MCP client at the command (see [deployment](deployment.md) for
Docker/HTTP and client configuration snippets), set `HH_TOKEN` in the server
environment for authorized tools. Public dictionaries, suggestions and
vacancy search work without a token.

## Toolsets

62 tools are enabled by default; six employer toolsets and the undocumented
extended set are opt-in via `HH_TOOLSETS`; `auth` is always on. The full
generated catalog with every tool, operation and description is in the
[tool reference](tools/index.md).

| Toolset | Tools | Default | Domain |
| --- | :---: | :---: | --- |
| `auth` | 5 | always on | `/me` profile, OAuth login/exchange/status/logout |
| `dictionaries` | 16 | on | areas, industries, professional roles, languages, metro, skills, universities |
| `suggests` | 11 | on | search suggestions: areas, companies, positions, skills, keywords |
| `vacancies` | 4 | on | vacancy search, similar and related vacancies |
| `negotiations` | 10 | on | responses/invitations: lists, states, messages, tests |
| `chats` | 14 | on | chats: messages, participants, files, read counters |
| `resumes` | 2 | on | resume viewing, call-tracking phone numbers |
| `employer_vacancies` | 23 | off | employer vacancy CRUD, drafts, publication, statistics |
| `employer_negotiations` | 5 | off | employer responses/invitations, mail templates |
| `employer_resumes` | 11 | off | resume search (52 params), saved searches, comments |
| `employer_managers` | 11 | off | managers, settings, access and limits |
| `employer_misc` | 25 | off | employers info, addresses, calls, webhooks, salary statistics |
| `extended` | 4 | off | **undocumented**: apply to a vacancy, own resumes, artifacts |

## How hh.ru authorization works

The server separates access to the MCP server (`Authorization: Bearer` with
an `MCP_API_KEYS` key, HTTP mode) from access to hh.ru (`X-HH-Token` header,
`HH_TOKEN` env, or an OAuth profile in SQLite). The [authorization
guide](deployment.md#oauth-login) covers the three token paths and hh.ru
application registration step by step.

## Where to go next

- [Tool reference](tools/index.md) – all 141 tools with operations and flags.
- [Architecture](architecture.md) – transports, registry, HHClient, TokenStore.
- [Configuration](configuration.md) – every environment variable.
- [Deployment](deployment.md) – Docker Compose, uvx, client snippets, OAuth.
- [Limitations](limitations.md) – honest boundaries of the hh.ru API coverage.
