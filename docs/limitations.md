# Limitations

Honest boundaries of what this server can do – all of them stem from the
hh.ru API itself or from deliberate safety decisions.

## hh.ru API boundaries

- **No resume CRUD.** The public hh.ru OpenAPI has no operations to create or
  edit resumes. The `resumes` toolset is read-only by design; the only way to
  list *your own* resumes is the undocumented `my_resumes` tool of the
  `extended` toolset.
- **The `extended` toolset is undocumented API.** `apply_to_vacancy`,
  `my_resumes`, `artifacts_list`, `artifact_delete` rely on endpoints outside
  the public specification. The toolset is disabled by default, every tool
  description carries the `[UNDOCUMENTED hh.ru API]` marker, and the
  operations may change or disappear without notice.
- **Search endpoints are geo-blocked** for datacenter IPs by hh.ru (403
  `forbidden`). This affects the fixture recorder when it runs from such
  networks – the server itself works fine from allowed networks.
- **The live API drifts from the specification.** Response bodies are
  validated against the vendored OpenAPI with live-recorded fixtures. The
  single confirmed deviation: `GET /suggests/companies` returns `null` in
  `url`, `area.name` and `logo_urls`, which the spec declares non-nullable.
  It is pinned in `KNOWN_DEVIATIONS` of `tests/contract/test_schemas.py`;
  the test fails if the entry rots (either the API heals or the deviation
  changes).

## Deliberate design decisions

- **Authorization header semantics.** `Authorization` carries the *MCP
  server* API key, not the hh.ru token; the hh.ru token travels in
  `X-HH-Token` or `HH_TOKEN`. This mirrors the two-tenant reality (access to
  the server vs access to hh.ru) and is an intentional deviation from the
  hh.ru API convention.
- **Retries are GET-only.** A timed-out mutation is reported as an error with
  a "may have been applied" hint and is never retried automatically: the
  operation might have succeeded on the hh.ru side.
- **Mutations require `confirm=true`.** A tool that changes state on hh.ru
  refuses to run without an explicit confirmation argument – an LLM cannot
  apply for a job or delete a message by accident.
- **Distribution is sources-only** (git + Docker): no PyPI package, no GHCR
  image – a project decision.

## Accepted deviations from the original plan

- **FastMCP 4.1** instead of "FastMCP 2": the concrete major was chosen in
  the M1 spike by stability and Python 3.10–3.14 support criteria and pinned
  in `uv.lock` ([ADR Z1](adr/Z1-fastmcp-major.md)).
- **`__main__` coverage floor is 90 %**, below the project-wide 95 %: the CLI
  entrypoint is a thin argument parser around fully tested components.
