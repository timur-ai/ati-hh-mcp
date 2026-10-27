# Configuration

Everything is configured through environment variables; there are no config
files. The same set applies to stdio and Docker/HTTP deployments.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HH_TOKEN` | – | hh.ru token applied to all calls (stdio path; ignored in HTTP mode when `MCP_API_KEYS` is set, to prevent mixing user profiles) |
| `HH_CLIENT_ID` | – | OAuth application client id from dev.hh.ru |
| `HH_CLIENT_SECRET` | – | OAuth application client secret |
| `HH_REDIRECT_URI` | – | OAuth redirect URI registered at dev.hh.ru (`http://<host>:8080/oauth/callback` for HTTP deployments) |
| `HH_TOOLSETS` | default set | Comma-separated extra toolsets to enable, e.g. `employer_vacancies,extended` |
| `HH_API_BASE` | `https://api.hh.ru` | API base URL (tests and experiments) |
| `HH_UA_EMAIL` | placeholder | Contact email embedded in the User-Agent header – an hh.ru requirement for API clients |
| `HH_RATE_LIMIT` | `25` | Requests per minute (token bucket, process-wide) |
| `HH_TOKEN_STORE` | platform dir | SQLite path for OAuth token pairs; the Docker image uses `/data/tokens.sqlite3` on a volume |
| `MCP_API_KEYS` | – | Comma-separated API keys guarding the HTTP endpoint (`Authorization: Bearer <key>`); each key gets an isolated OAuth profile |

## Toolset selection

Default toolsets (62 tools including the always-on `auth`): `dictionaries`,
`suggests`, `vacancies`, `negotiations`, `chats`, `resumes`.

Opt-in toolsets: `employer_vacancies`, `employer_negotiations`,
`employer_resumes`, `employer_managers`, `employer_misc`, `extended`
(undocumented API). Example:

```bash
HH_TOOLSETS=employer_vacancies,employer_resumes ati-hh-mcp serve --transport stdio
```

Unknown or not-yet-implemented names are skipped silently, so a config keeps
working across versions.

## Token precedence

For each call the hh.ru token is selected as:

1. `X-HH-Token` request header (HTTP mode, stateless, never stored);
2. the OAuth profile of the caller (per MCP API key, SQLite);
3. `HH_TOKEN` environment variable (disabled in HTTP mode with
   `MCP_API_KEYS`).
