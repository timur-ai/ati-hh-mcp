# Deployment

Two supported paths: **uvx from git** (stdio, personal) and **Docker Compose**
(HTTP, teams). A repository clone is not needed for either.

## TLS is mandatory for network exposure

`Authorization: Bearer` headers (your MCP API key and hh.ru tokens in
`X-HH-Token`) must never cross an unencrypted network. Rules:

- The server speaks plain HTTP; put a TLS-terminating reverse proxy in front
  whenever it is reachable beyond `127.0.0.1`.
- The server refuses to start in HTTP mode without `MCP_API_KEYS` on a
  non-loopback host (use `--host 127.0.0.1` for personal runs).
- Bind Docker to loopback and let the proxy own the public port
  (`ports: ["127.0.0.1:8080:8080"]` – commented variant in
  `docker-compose.yml`).
- Run **one worker process**: the SQLite token store assumes a single
  process (WAL); scaling out requires an external store.

Caddy one-liner (automatic HTTPS):

```bash
caddy reverse-proxy --from hh-mcp.example.com --to 127.0.0.1:8080
```

nginx equivalent:

```nginx
server {
    listen 443 ssl http2;
    server_name hh-mcp.example.com;
    ssl_certificate     /etc/letsencrypt/live/hh-mcp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/hh-mcp.example.com/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_buffering off;   # streamable HTTP / SSE
    }
}
```

## uvx from git (stdio)

```bash
uvx --from git+https://github.com/timur-ai/ati-hh-mcp ati-hh-mcp serve --transport stdio
```

Pin a commit for reproducibility:

```bash
uvx --from git+https://github.com/timur-ai/ati-hh-mcp@<sha> ati-hh-mcp serve --transport stdio
```

The CI pipeline verifies this exact path (install from git + MCP initialize +
`tools/list`) on every push.

## Docker Compose (HTTP)

```bash
git clone https://github.com/timur-ai/ati-hh-mcp
cd ati-hh-mcp
MCP_API_KEYS="$(openssl rand -hex 32)" docker compose up --build
```

The container:

- listens on `8080` (MCP endpoint `http://<host>:8080/mcp`, health check
  `GET /health`);
- runs as a non-root user;
- keeps OAuth tokens in the `hh-tokens` volume (`/data/tokens.sqlite3`);
- requires `MCP_API_KEYS` in multi-user setups – every client then sends
  `Authorization: Bearer <key>` and gets an isolated OAuth profile (keys are
  case-sensitive).

Build straight from sources without Compose:

```bash
docker build -t ati-hh-mcp .
docker run -p 8080:8080 -e MCP_API_KEYS=my-key -e HH_UA_EMAIL=you@example.com ati-hh-mcp
```

## Client configuration snippets

### ZCode (stdio)

`.zcode/settings.json`:

```json
{
  "mcpServers": {
    "hh": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/timur-ai/ati-hh-mcp",
        "ati-hh-mcp", "serve", "--transport", "stdio"
      ],
      "env": {
        "HH_TOKEN": "YOUR_HH_TOKEN",
        "HH_UA_EMAIL": "you@example.com"
      }
    }
  }
}
```

### Claude Desktop (stdio)

`claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`,
Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "hh": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/timur-ai/ati-hh-mcp",
        "ati-hh-mcp", "serve", "--transport", "stdio"
      ],
      "env": {
        "HH_TOKEN": "YOUR_HH_TOKEN",
        "HH_UA_EMAIL": "you@example.com"
      }
    }
  }
}
```

### Cursor (stdio)

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "hh": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/timur-ai/ati-hh-mcp",
        "ati-hh-mcp", "serve", "--transport", "stdio"
      ],
      "env": {
        "HH_TOKEN": "YOUR_HH_TOKEN",
        "HH_UA_EMAIL": "you@example.com"
      }
    }
  }
}
```

### Any client (HTTP)

```json
{
  "mcpServers": {
    "hh": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_API_KEY"
      }
    }
  }
}
```

A per-request hh.ru token can be added as `"X-HH-Token": "..."` in the same
`headers` object.

## OAuth login

With `HH_CLIENT_ID`, `HH_CLIENT_SECRET`, `HH_REDIRECT_URI` set:

- **stdio**: call `auth_get_login_url`, open the URL, log in on hh.ru, copy
  the `code` parameter from the redirect address, call
  `auth_exchange_code(code)`.
- **HTTP**: open the same login URL; the redirect lands on
  `GET /oauth/callback` of the server and the exchange completes
  automatically. The `state` parameter binds the flow to the caller's API-key
  profile, so tokens land in the right SQLite profile.

`auth_status` inspects the profile; `auth_logout` revokes the pair on hh.ru
(`DELETE /token`) and clears the store.

### Registering an hh.ru application

1. Sign in at [dev.hh.ru](https://dev.hh.ru), open the application admin.
2. Create an application → `HH_CLIENT_ID`, `HH_CLIENT_SECRET`.
3. Register the redirect URI: `http://<your-host>:8080/oauth/callback`
   (`http://localhost:8080/oauth/callback` for local testing). For stdio any
   previously registered URI works – the code is copied manually.
4. Set the three `HH_*` variables in the server environment and restart.
