"""Mapping facades over agent definitions on disk.

COACT_SPEC §8 ("prefer Mapping/MutableMapping facades — a skills store, an
agents store") mirroring ``skill.stores.LocalSkillStore``. :class:`AgentStore`
is a ``MutableMapping[str, AgentDefinition]`` over a ``.claude/agents/``
directory (one ``<name>.md`` per agent). Because it is a plain mapping, it drops
straight into ``py2mcp.mk_mcp_from_store`` to expose a project's agents as CRUD
over MCP, and into ``coact.analysis.inventory``.
"""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from pathlib import Path

from skill.util import find_project_root

from coact.base import AgentDefinition
from coact.emit import from_claude_agent_md, to_claude_agent_md


def agents_dir(
    *, scope: str = "project", project_dir: Path | str | None = None
) -> Path:
    """Resolve the ``.claude/agents`` directory for the given scope.

    ``scope='project'`` resolves against the detected project root (or
    ``project_dir``); ``scope='global'`` resolves against ``~/.claude``.

    >>> agents_dir(scope='global').as_posix().endswith('.claude/agents')
    True
    """
    if scope == "global":
        return Path.home() / ".claude" / "agents"
    root = Path(project_dir) if project_dir is not None else find_project_root()
    if root is None:
        root = Path.cwd()
    return Path(root) / ".claude" / "agents"


class AgentStore(MutableMapping[str, AgentDefinition]):
    """A ``MutableMapping[str, AgentDefinition]`` over a ``.claude/agents/`` dir.

    Keys are agent names; each agent is one ``<name>.md`` file.

    >>> import tempfile
    >>> from coact.base import AgentDefinition
    >>> store = AgentStore(root=tempfile.mkdtemp())
    >>> store['ux'] = AgentDefinition(name='ux', description='Analyze.', prompt='You are...')
    >>> list(store)
    ['ux']
    >>> store['ux'].description
    'Analyze.'
    >>> del store['ux']
    >>> len(store)
    0
    """

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        scope: str = "project",
        project_dir: Path | str | None = None,
    ):
        self.root = (
            Path(root)
            if root is not None
            else agents_dir(scope=scope, project_dir=project_dir)
        )
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / f"{name}.md"

    def __getitem__(self, name: str) -> AgentDefinition:
        path = self._path(name)
        if not path.exists():
            raise KeyError(name)
        return from_claude_agent_md(path.read_text())

    def __setitem__(self, name: str, agent: AgentDefinition) -> None:
        self._path(name).write_text(to_claude_agent_md(agent))

    def __delitem__(self, name: str) -> None:
        path = self._path(name)
        if not path.exists():
            raise KeyError(name)
        path.unlink()

    def __iter__(self) -> Iterator[str]:
        if not self.root.exists():
            return
        for child in sorted(self.root.glob("*.md")):
            yield child.stem

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self._path(name).exists()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(root={self.root!r})"
