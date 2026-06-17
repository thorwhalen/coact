"""``claude-remote-connector`` publish target — scaffold a deployable **remote**
Claude connector (a public Streamable-HTTP MCP server with OAuth 2.1).

A claude.ai **custom connector** is a *remote* MCP server reached from Anthropic's
cloud over public HTTPS — even on Desktop — so it needs a publicly-reachable
endpoint and **OAuth 2.1**. That is a different surface from the local
``.mcpb``/stdio target (:mod:`coact.publish_mcpb`): different transport, different
auth, different place it runs. This target produces a **deployment scaffold** (a
small project you host), not a single file.

Division of labour (mirrors the ``.mcpb`` path and DECISIONS D17/D19): coact
writes only *packaging/deploy scaffolding*; the MCP server itself — Streamable
HTTP + the OAuth 2.1 **resource-server** wiring — is built by ``py2mcp``'s
:func:`py2mcp.http.mk_http_app`. So building the scaffold is **pure stdlib**
(``json`` only); ``py2mcp``/``fastmcp``/``uvicorn`` are needed only in the Python
that *runs* the deployed service, and a missing one is a warning, not a build error.

Security posture baked into the scaffold (landscape doc §4.4/§8.5): the server is
an OAuth 2.1 **resource server** that *validates* a managed IdP's tokens (never an
authorization server of its own), tokens are **audience-bound** (RFC 8707) so one
minted for another service can't be replayed, and the server **never forwards** an
inbound token upstream (no confused-deputy). The connector binds locally and must
sit behind a TLS-terminating reverse proxy.
"""

from __future__ import annotations

import json
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Optional

from coact.integration import IntegrationSource, IntegrationSpec, integration_spec_from
from coact.publish import PublishResult, targets
from coact.util import safe_filename

#: Placeholder host used in the emitted config when no real connector URL is given.
_PLACEHOLDER_HOST = "https://YOUR-CONNECTOR.example.com"
#: Placeholder IdP issuer used when no managed IdP is configured yet.
_PLACEHOLDER_IDP = "https://YOUR-IDP.example.com"

#: The generated ``server/app.py`` — an ASGI app any ASGI server can run.
_SERVER_APP = '''\
"""ASGI entry point for a coact-scaffolded remote Claude connector.

Serves a py2mcp MCP server over Streamable HTTP with OAuth 2.1 (a resource
server). Run behind TLS, e.g.:

    uvicorn server.app:app --host 127.0.0.1 --port 8000

Requires `py2mcp` (>=0.1.4), `fastmcp`, and an ASGI server (uvicorn) importable.
"""
import json
import os

from py2mcp.http import mk_http_app

_CONFIG = os.path.join(os.path.dirname(__file__), "{config_name}")
with open(_CONFIG) as _f:
    _cfg = json.load(_f)

app = mk_http_app(
    _cfg["refs"],
    name=_cfg.get("name", "connector"),
    auth=_cfg.get("auth"),
    transport=_cfg.get("transport", "streamable-http"),
    stateless_http=_cfg.get("stateless_http", True),
)
'''

#: Name of the bundled connector config, under ``server/``.
SERVER_CONFIG_NAME = "connector_config.json"
_SERVER_APP = _SERVER_APP.format(config_name=SERVER_CONFIG_NAME)

_REQUIREMENTS = "py2mcp>=0.1.4\nfastmcp>=3\nuvicorn[standard]>=0.27\n"

_DOCKERFILE = '''\
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
# Bind locally; terminate TLS at your reverse proxy / platform.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
'''


def publish_remote(
    source: IntegrationSource,
    *,
    dest: Optional[str] = None,
    dry_run: bool = False,
    name: Optional[str] = None,
    author: Optional[str] = None,
    version: str = "0.1.0",
    description: str = "",
    connector_url: Optional[str] = None,
    idp_issuer: Optional[str] = None,
    jwks_uri: Optional[str] = None,
    audience: Optional[str] = None,
    required_scopes: Optional[list] = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    transport: str = "streamable-http",
    include_dockerfile: bool = True,
) -> PublishResult:
    """Scaffold a remote Claude connector (Streamable-HTTP MCP server + OAuth 2.1).

    ``source`` is anything :func:`coact.integration.integration_spec_from` accepts.
    The OAuth parameters describe the **managed IdP** that issues tokens and *this*
    server's public identity; when omitted, placeholder values + a loud warning are
    emitted so the scaffold is still useful (fill them in before going public).

    >>> res = publish_remote(['os.path:basename'], name='paths', dry_run=True)
    >>> res.dry_run, sorted(res.files)  # doctest: +NORMALIZE_WHITESPACE
    (True, ['DEPLOY.md', 'Dockerfile', 'requirements.txt', 'server/app.py',
            'server/connector_config.json'])
    """
    spec = integration_spec_from(
        source, name=name, author=author, version=version, description=description
    )
    spec.auth = "oauth2.1"
    spec.deployment = "remote-http"
    if spec.is_empty():
        raise ValueError("nothing to publish: the IntegrationSpec carries no tools.")

    runnable_refs = spec.runnable_refs()
    if not runnable_refs:
        proposed = ", ".join(ts.name for ts in spec.tool_specs) or "(none)"
        raise ValueError(
            f"This IntegrationSpec is a design draft: {len(spec.tool_specs)} "
            f"proposed tool(s) [{proposed}], none bound to an importable "
            "'module:function' handler. Bind handlers (or pass refs) before "
            "scaffolding a runnable remote connector (see `coact describe`)."
        )

    auth, auth_warnings = _build_auth(
        connector_url=connector_url,
        idp_issuer=idp_issuer,
        jwks_uri=jwks_uri,
        audience=audience,
        required_scopes=required_scopes,
    )
    config = {
        "name": spec.name,
        "refs": runnable_refs,
        "host": host,
        "port": port,
        "transport": transport,
        "stateless_http": True,
        "auth": auth,
    }
    members = {
        "server/app.py": _SERVER_APP,
        f"server/{SERVER_CONFIG_NAME}": json.dumps(config, indent=2),
        "requirements.txt": _REQUIREMENTS,
        "DEPLOY.md": _deploy_md(spec, auth, connector_url=connector_url),
    }
    if include_dockerfile:
        members["Dockerfile"] = _DOCKERFILE

    warnings = list(auth_warnings)
    if find_spec("py2mcp") is None:
        warnings.append(
            "py2mcp is not importable here; the deployed service needs `py2mcp` "
            ">=0.1.4, `fastmcp`, and `uvicorn` installed where it runs."
        )

    dir_name = safe_filename(spec.name, suffix="-connector", kind="integration name")
    instructions = _install_instructions(dir_name)
    previews = {rel: _preview(content) for rel, content in members.items()}

    if dry_run:
        return PublishResult(
            target="claude-remote-connector",
            dry_run=True,
            files=previews,
            instructions=instructions,
            warnings=warnings,
        )

    dest_dir = (Path(dest) if dest is not None else Path.cwd()) / dir_name
    for rel, content in members.items():
        out = dest_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content)

    return PublishResult(
        target="claude-remote-connector",
        dry_run=False,
        artifact=dest_dir,
        files=previews,
        instructions=instructions,
        warnings=warnings,
    )


def _build_auth(
    *,
    connector_url: Optional[str],
    idp_issuer: Optional[str],
    jwks_uri: Optional[str],
    audience: Optional[str],
    required_scopes: Optional[list],
) -> tuple[dict, list[str]]:
    """Build the ``auth`` config block (resource-server, ``type='jwt'``) + warnings.

    A fully-specified IdP yields a ready config; missing pieces yield clearly-marked
    placeholders plus a loud warning — a remote connector MUST require OAuth 2.1, so
    we never silently emit an unauthenticated config.
    """
    warnings: list[str] = []
    base_url = connector_url or _PLACEHOLDER_HOST
    issuer = idp_issuer or _PLACEHOLDER_IDP
    resolved_jwks = jwks_uri or f"{issuer.rstrip('/')}/.well-known/jwks.json"
    resolved_aud = audience or f"{base_url.rstrip('/')}/mcp"

    missing = [
        label
        for label, value in (("connector_url", connector_url), ("idp_issuer", idp_issuer))
        if not value
    ]
    if missing:
        warnings.append(
            "OAuth is NOT fully configured ("
            + ", ".join(f"missing {m}" for m in missing)
            + "): placeholder values were written to "
            f"server/{SERVER_CONFIG_NAME}. A remote connector MUST require OAuth "
            "2.1 — set your managed IdP (issuer + JWKS) and this connector's public "
            "URL before exposing it. See DEPLOY.md."
        )

    auth = {
        "type": "jwt",
        "jwks_uri": resolved_jwks,
        "issuer": issuer,
        "audience": resolved_aud,
        "authorization_servers": [issuer],
        "base_url": base_url,
        "required_scopes": list(required_scopes or []),
    }
    return auth, warnings


def _deploy_md(
    spec: IntegrationSpec, auth: dict, *, connector_url: Optional[str]
) -> str:
    """The DEPLOY.md guide bundled with the scaffold (deploy + security + register)."""
    tools = ", ".join(spec.runnable_refs())
    return f"""# Deploy: {spec.name} — remote Claude connector

This is a **remote** MCP server (Streamable HTTP + OAuth 2.1) — a claude.ai
*custom connector*. It is reached from Anthropic's cloud over public **HTTPS**,
so it must be publicly reachable and authenticated. (This is *not* a local
`.mcpb` extension; that is a separate, local-stdio surface.)

Tools exposed: {tools}

## 1. Prerequisites

```bash
pip install -r requirements.txt   # py2mcp, fastmcp, uvicorn
```

## 2. Configure OAuth 2.1 (resource-server pattern)

This server is an OAuth 2.1 **resource server**: it *validates* access tokens
issued by a **managed identity provider** (the authorization server) — it never
issues tokens itself. Use a managed IdP (Auth0, WorkOS AuthKit, Azure AD, Google,
Okta, …); **do not roll your own authorization server.**

Edit `server/{SERVER_CONFIG_NAME}` → `auth`:

- `issuer` / `authorization_servers`: your IdP's issuer URL.
- `jwks_uri`: the IdP's JWKS endpoint (signing keys).
- `audience`: **this** connector's resource id (its public URL) — the token's
  `aud`. This audience binding (RFC 8707) is what stops a token minted for another
  service being replayed here. Current value: `{auth['audience']}`.
- `base_url`: this connector's public base URL.
- `required_scopes`: scopes every request must carry (optional).

The server publishes `/.well-known/oauth-protected-resource` (RFC 9728) pointing
clients at your IdP automatically — you do not write it.

## 3. Run behind TLS

```bash
uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Bind to localhost and terminate **HTTPS at a reverse proxy** (nginx/Caddy) or your
platform. A VPN-only/firewalled server cannot be a connector — Anthropic's cloud
connects from public IPs. For horizontal scale keep `stateless_http: true` (set)
or externalize session state; avoid sticky sessions.

Container option: `docker build -t {spec.name}-connector . && docker run -p 8000:8000 {spec.name}-connector`
(still front it with TLS).

## 4. Register in claude.ai

Settings → Connectors → "Add custom connector" → enter your **public HTTPS URL**
(e.g. `{connector_url or _PLACEHOLDER_HOST}/mcp`). Claude runs the OAuth flow against
your IdP. (Team/Enterprise admins can manage org-wide.)

## 5. Security checklist (designed in, not bolted on)

- Resource server **only** — never an authorization server; tokens come from the IdP.
- **Validate the token audience**; the server **never forwards** an inbound token
  upstream (no confused-deputy). Any upstream call your tools make uses its own creds.
- Least-privilege scopes; human approval for write/destructive tools.
- Never bake secrets into the config/repo — use env / your platform's secret store.
- Keep `fastmcp` patched (OAuth/transport CVEs have history).
"""


def _install_instructions(dir_name: str) -> str:
    """Human next-steps for the produced scaffold."""
    return (
        f"Scaffolded {dir_name!r}: a REMOTE Claude connector (Streamable HTTP + "
        "OAuth 2.1). Next: configure your managed IdP + this connector's public URL "
        f"in {dir_name}/server/{SERVER_CONFIG_NAME}, run it behind TLS "
        "(uvicorn server.app:app), then add its HTTPS URL as a custom connector in "
        "claude.ai. Full guide: DEPLOY.md. This is NOT a local .mcpb — it runs as a "
        "hosted service reached from Anthropic's cloud."
    )


def _preview(content: str, *, limit: int = 200) -> str:
    """A one-line, length-bounded preview of a scaffold member's content."""
    text = " ".join((content if isinstance(content, str) else repr(content)).split())
    return text if len(text) <= limit else text[:limit] + "…"


targets.register("claude-remote-connector", publish_remote)
