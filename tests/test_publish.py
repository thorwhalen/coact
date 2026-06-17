"""Tests for the PUBLISH axis (IntegrationSpec + publish + claude-local-mcpb)."""

import json
import zipfile

import pytest

from coact import (
    IntegrationSpec,
    ToolSpec,
    integration_spec_from,
    publish,
    publish_mcpb,
    publish_targets,
)
from coact.publish_mcpb import MCPB_MANIFEST_VERSION


def sample_tool(x: int) -> int:
    """Double the input."""
    return x * 2


# --- ingress: integration_spec_from -----------------------------------------


def test_target_registered():
    assert "claude-local-mcpb" in publish_targets()


def test_spec_from_refs():
    spec = integration_spec_from(["os.path:basename", "os.path:dirname"], name="paths")
    assert spec.name == "paths"
    assert spec.tools == ["os.path:basename", "os.path:dirname"]
    assert spec.deployment == "local-stdio"
    assert not spec.is_empty()


def test_spec_name_is_kebabbed():
    assert integration_spec_from(["a:b"], name="My Cool Tools").name == "my-cool-tools"


def test_spec_from_callable():
    spec = integration_spec_from(sample_tool)
    assert spec.tools[0].endswith(":sample_tool")
    assert spec.name == "sample-tool"


def test_spec_from_skill_dir(tmp_path):
    skill_dir = tmp_path / "paths-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: paths-skill\n"
        "description: Path tools.\n"
        "coact:\n"
        "  mcp:\n"
        "    - module: os.path\n"
        "      functions: [basename, dirname]\n"
        "---\n"
        "body\n"
    )
    spec = integration_spec_from(str(skill_dir))
    assert spec.name == "paths-skill"
    assert spec.tools == ["os.path:basename", "os.path:dirname"]


def test_spec_no_tools_raises():
    with pytest.raises(ValueError):
        integration_spec_from([])


# --- publish: dry-run --------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path):
    res = publish(
        ["os.path:basename"],
        target="claude-local-mcpb",
        name="paths",
        dest=str(tmp_path),
        dry_run=True,
    )
    assert res.dry_run is True
    assert res.artifact is None
    assert set(res.files) == {
        "manifest.json",
        "server/main.py",
        "server/py2mcp_config.json",
    }
    assert list(tmp_path.iterdir()) == []  # nothing written


# --- publish: real bundle ----------------------------------------------------


def test_publish_writes_valid_mcpb(tmp_path):
    res = publish(
        ["os.path:basename", "os.path:dirname"], name="paths", dest=str(tmp_path)
    )
    assert res.dry_run is False
    assert res.artifact is not None and res.artifact.exists()
    assert res.artifact.name == "paths.mcpb"

    with zipfile.ZipFile(res.artifact) as zf:
        names = set(zf.namelist())
        assert {
            "manifest.json",
            "server/main.py",
            "server/py2mcp_config.json",
        } <= names
        manifest = json.loads(zf.read("manifest.json"))
        cfg = json.loads(zf.read("server/py2mcp_config.json"))
        server_main = zf.read("server/main.py").decode()

    assert manifest["manifest_version"] == MCPB_MANIFEST_VERSION
    assert manifest["name"] == "paths"
    assert manifest["server"]["type"] == "python"
    assert manifest["server"]["mcp_config"]["args"] == ["${__dirname}/server/main.py"]
    assert cfg == {"name": "paths", "refs": ["os.path:basename", "os.path:dirname"]}
    # tool metadata introspected from the functions' docstrings
    tool_names = {t["name"] for t in manifest["tools"]}
    assert {"basename", "dirname"} <= tool_names
    # the server shim launches py2mcp's stdio runner against the bundled config
    assert "py2mcp.serve" in server_main
    assert "py2mcp_config.json" in server_main


def test_unsafe_name_rejected(tmp_path):
    with pytest.raises(ValueError):
        publish(["os.path:basename"], name="../evil", dest=str(tmp_path))


def test_empty_spec_rejected():
    with pytest.raises(ValueError):
        publish_mcpb(IntegrationSpec(name="empty"))


def test_unknown_target_rejected():
    with pytest.raises(ValueError):
        publish(["os.path:basename"], target="no-such-target")


# --- robustness (adversarial-review hardening) -------------------------------


class _Box:
    def tool(self) -> int:
        """A bound method, not importable by reference."""
        return 1


def test_bound_method_rejected():
    with pytest.raises(ValueError):
        integration_spec_from(_Box().tool)


def test_unrecognized_source_raises():
    # a dotted name (no colon) that isn't a path must not be silently dropped
    with pytest.raises(ValueError):
        integration_spec_from(["os.path:basename", "os.path.basename"])


def test_duplicate_tool_names_warn(tmp_path):
    res = publish(
        ["os.path:basename", "posixpath:basename"],
        name="dups",
        dest=str(tmp_path),
        dry_run=True,
    )
    assert any("duplicate tool name" in w for w in res.warnings)


# --- ToolSpec / draft mechanics (oa-free; run in CI) -------------------------
# These cover the IntegrationSpec/publish-axis half of the NL ingress without
# needing the oa backend, so they run in bare CI (the oa-dependent ingress tests
# live in test_nl_ingress.py under importorskip("oa")).


def test_proposed_tools_listed_in_manifest_with_warning(tmp_path):
    # a bound tool (publishable) plus an unbound proposed tool
    spec = IntegrationSpec(
        name="mix",
        tool_specs=[
            ToolSpec(name="basename", handler="os.path:basename"),
            ToolSpec(name="future_tool", description="not built yet"),
        ],
    )
    res = publish(spec, dest=str(tmp_path), dry_run=True)
    assert any("future_tool" in w for w in res.warnings)


def test_spec_in_list_preserves_bound_handlers():
    # #5 (high): a draft mixed into a list must not lose its bound handlers
    draft = IntegrationSpec(
        name="wx", tool_specs=[ToolSpec(name="dn", handler="os.path:dirname")]
    )
    out = integration_spec_from([draft, "os.path:basename"])
    assert "os.path:dirname" in out.runnable_refs()
    assert "os.path:basename" in out.runnable_refs()


def test_pure_bound_draft_in_list_publishes(tmp_path):
    draft = IntegrationSpec(
        name="wx", tool_specs=[ToolSpec(name="bn", handler="os.path:basename")]
    )
    out = integration_spec_from([draft])
    assert out.runnable_refs() == ["os.path:basename"]
    res = publish(out, dest=str(tmp_path))
    assert res.artifact is not None and res.artifact.exists()


def test_bound_toolspec_fills_empty_manifest_description(monkeypatch):
    """A bound tool whose docstring is empty gets its manifest desc from the ToolSpec."""
    import importlib

    pm = importlib.import_module("coact.publish_mcpb")
    monkeypatch.setattr(
        pm, "_introspect_tools", lambda refs: ([{"name": "basename", "description": ""}], [])
    )
    spec = IntegrationSpec(
        name="mix",
        tool_specs=[ToolSpec(name="x", description="curated", handler="os.path:basename")],
    )
    manifest, _ = pm.build_manifest(spec)
    tool = next(t for t in manifest["tools"] if t["name"] == "basename")
    assert tool["description"] == "curated"  # empty introspected desc filled in


def test_bound_toolspec_does_not_clobber_introspected_description(monkeypatch):
    """Runtime truth (the function's own docstring) wins — never desync manifest vs server."""
    import importlib

    pm = importlib.import_module("coact.publish_mcpb")
    monkeypatch.setattr(
        pm,
        "_introspect_tools",
        lambda refs: ([{"name": "basename", "description": "real docstring"}], []),
    )
    spec = IntegrationSpec(
        name="mix",
        tool_specs=[ToolSpec(name="x", description="curated", handler="os.path:basename")],
    )
    manifest, _ = pm.build_manifest(spec)
    tool = next(t for t in manifest["tools"] if t["name"] == "basename")
    assert tool["description"] == "real docstring"


def test_resources_only_spec_rejected_with_clear_message():
    with pytest.raises(ValueError, match="resource"):
        publish_mcpb(IntegrationSpec(name="r", resources=["data1"]))


def test_import_coact_is_provider_free():
    """D10/D18: `import coact` must not pull in oa/aix/litellm (lazy provider deps)."""
    import subprocess
    import sys

    code = (
        "import sys, coact; "
        "leaked=[m for m in ('oa','aix','litellm','openai') if m in sys.modules]; "
        "assert not leaked, leaked; print('ok')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"
