"""Tests for the claude-remote-connector publish target.

Building the scaffold is pure stdlib (no py2mcp/fastmcp import), so these run
offline and assert on the emitted files' content.
"""

import json

import pytest

from coact import (
    IntegrationSpec,
    ToolSpec,
    publish,
    publish_remote,
    publish_targets,
)
from coact.publish_remote import SERVER_CONFIG_NAME

_MEMBERS = {
    "DEPLOY.md",
    "Dockerfile",
    "requirements.txt",
    "server/app.py",
    f"server/{SERVER_CONFIG_NAME}",
}


def test_target_registered():
    assert "claude-remote-connector" in publish_targets()


def test_dry_run_writes_nothing(tmp_path):
    res = publish(
        ["os.path:basename"],
        target="claude-remote-connector",
        name="paths",
        dest=str(tmp_path),
        dry_run=True,
    )
    assert res.dry_run is True
    assert res.artifact is None
    assert set(res.files) == _MEMBERS
    assert list(tmp_path.iterdir()) == []  # nothing written


def test_writes_scaffold_dir(tmp_path):
    res = publish_remote(
        ["os.path:basename", "os.path:dirname"],
        name="paths",
        dest=str(tmp_path),
        connector_url="https://conn.example.com",
        idp_issuer="https://idp.example.com",
        required_scopes=["mcp:read"],
    )
    assert res.artifact is not None and res.artifact.is_dir()
    assert res.artifact.name == "paths-connector"
    written = {str(p.relative_to(res.artifact)) for p in res.artifact.rglob("*") if p.is_file()}
    # rglob uses OS sep; normalize
    written = {w.replace("\\", "/") for w in written}
    assert _MEMBERS <= written

    cfg = json.loads((res.artifact / "server" / SERVER_CONFIG_NAME).read_text())
    assert cfg["refs"] == ["os.path:basename", "os.path:dirname"]
    assert cfg["transport"] == "streamable-http"
    assert cfg["stateless_http"] is True
    auth = cfg["auth"]
    assert auth["type"] == "jwt"
    assert auth["issuer"] == "https://idp.example.com"
    assert auth["authorization_servers"] == ["https://idp.example.com"]
    assert auth["base_url"] == "https://conn.example.com"
    # audience defaults to connector_url + /mcp (RFC 8707 resource binding)
    assert auth["audience"] == "https://conn.example.com/mcp"
    # jwks defaults under the issuer
    assert auth["jwks_uri"] == "https://idp.example.com/.well-known/jwks.json"
    assert auth["required_scopes"] == ["mcp:read"]

    app = (res.artifact / "server" / "app.py").read_text()
    assert "py2mcp.http" in app and "mk_http_app" in app


def test_fully_configured_has_no_oauth_warning(tmp_path):
    res = publish_remote(
        ["os.path:basename"],
        name="ok",
        dest=str(tmp_path),
        connector_url="https://conn.example.com",
        idp_issuer="https://idp.example.com",
    )
    assert not any("OAuth is NOT fully configured" in w for w in res.warnings)


def test_unconfigured_oauth_warns_and_uses_placeholders(tmp_path):
    res = publish_remote(["os.path:basename"], name="todo", dest=str(tmp_path))
    assert any("OAuth is NOT fully configured" in w for w in res.warnings)
    auth = json.loads((res.artifact / "server" / SERVER_CONFIG_NAME).read_text())["auth"]
    assert "YOUR-IDP" in auth["issuer"]  # placeholder emitted, not a silent unauthenticated config
    assert auth["type"] == "jwt"


def test_explicit_audience_and_jwks_override(tmp_path):
    res = publish_remote(
        ["os.path:basename"],
        name="x",
        dest=str(tmp_path),
        connector_url="https://conn.example.com",
        idp_issuer="https://idp.example.com",
        audience="https://conn.example.com/custom-aud",
        jwks_uri="https://idp.example.com/keys",
    )
    auth = json.loads((res.artifact / "server" / SERVER_CONFIG_NAME).read_text())["auth"]
    assert auth["audience"] == "https://conn.example.com/custom-aud"
    assert auth["jwks_uri"] == "https://idp.example.com/keys"


def test_no_dockerfile_when_disabled():
    res = publish_remote(["os.path:basename"], name="x", dry_run=True, include_dockerfile=False)
    assert "Dockerfile" not in res.files
    assert "server/app.py" in res.files


def test_pure_draft_rejected():
    spec = IntegrationSpec(name="d", tool_specs=[ToolSpec(name="t")])  # no handler
    with pytest.raises(ValueError, match="design draft"):
        publish_remote(spec)


def test_empty_rejected():
    with pytest.raises(ValueError):
        publish_remote(IntegrationSpec(name="empty"))


def test_unsafe_name_rejected(tmp_path):
    with pytest.raises(ValueError):
        publish_remote(["os.path:basename"], name="../evil", dest=str(tmp_path))


def test_bound_draft_scaffolds(tmp_path):
    # a draft whose tools are bound to real refs is a valid remote source
    spec = IntegrationSpec(name="wx", tool_specs=[ToolSpec(name="bn", handler="os.path:basename")])
    res = publish_remote(
        spec, dest=str(tmp_path), connector_url="https://c.example.com", idp_issuer="https://i.example.com"
    )
    cfg = json.loads((res.artifact / "server" / SERVER_CONFIG_NAME).read_text())
    assert cfg["refs"] == ["os.path:basename"]


def test_scaffolded_app_builds_real_authed_asgi_app(tmp_path):
    """End-to-end (dev only): the generated server/app.py builds a real ASGI app.

    Skipped in bare CI (py2mcp/fastmcp are the [mcpb] extra, not installed there);
    proves the scaffold is runnable, not just well-shaped.
    """
    pytest.importorskip("py2mcp")
    pytest.importorskip("fastmcp")
    import importlib.util

    res = publish_remote(
        ["os.path:basename"],
        name="paths",
        dest=str(tmp_path),
        connector_url="https://conn.example.com",
        idp_issuer="https://idp.example.com",
        required_scopes=["mcp:read"],
    )
    app_path = res.artifact / "server" / "app.py"
    spec = importlib.util.spec_from_file_location("scaffolded_connector_app", app_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # reads connector_config.json next to app.py
    assert callable(mod.app)  # a Starlette ASGI app, with OAuth attached, built offline
    assert hasattr(mod.app, "routes")
