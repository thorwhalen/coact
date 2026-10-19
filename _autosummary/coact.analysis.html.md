# coact.analysis

Analysis utilities — small tools to *see and move between* the layers.

COACT_SPEC §7. Thin tooling around the two transforms:

- [`diff()`](#coact.analysis.diff) — what extras an agent adds over its source skill (audit drift
  between the SSOT skill and a derived agent).
- [`estimate()`](#coact.analysis.estimate) — the §3.5 / DECISIONS-D9 cost gate: the implied fan-out token
  multiplier of an agent set, flagging interdependent sets where multi-agent is a
  poor fit.
- [`inventory()`](#coact.analysis.inventory) — enumerate a project’s reusable AI assets: skills, derived
  agents, and MCP-exposed tools (reuses `skill` discovery; adds the agent + MCP
  dimensions).
- [`back()`](#coact.analysis.back) — best-effort, **lossy** agent→skill extraction (harvest an ad-hoc
  agent back into reusable procedural knowledge).

### Functions

| [`back`](#coact.analysis.back)(agent)          | Best-effort, **lossy** agent→skill extraction (harvest an agent into a skill).   |
|-----------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`diff`](#coact.analysis.diff)(skill, agent)   | Show what extras `agent` adds over its source `skill`.                           |
| [`estimate`](#coact.analysis.estimate)(agents)     | Surface the fan-out cost tradeoff for an agent set (DECISIONS D9).               |
| [`inventory`](#coact.analysis.inventory)([project]) | Enumerate skills, derived agents, and MCP-exposed tools in a project.            |

### Classes

| [`AgentDiff`](#coact.analysis.AgentDiff)(skill_name, agent_name[, rows])       | What a derived agent adds over its source skill.                        |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`Estimate`](#coact.analysis.Estimate)(n_agents, interdependent, ...)         | The implied cost tradeoff of realizing an agent set as a running fleet. |
| [`Inventory`](#coact.analysis.Inventory)(project[, skills, agents, mcp_tools]) | One picture of a project's reusable AI assets.                          |

### *class* coact.analysis.AgentDiff(skill_name, agent_name, rows=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a derived agent adds over its source skill.

#### render()

Render the extras table for terminal display.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *class* coact.analysis.Estimate(n_agents, interdependent, shared_skills, token_multiplier_vs_chat, recommendation)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The implied cost tradeoff of realizing an agent set as a running fleet.

#### render()

Render the cost gate for terminal display.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### *class* coact.analysis.Inventory(project, skills=list(), agents=list(), mcp_tools=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One picture of a project’s reusable AI assets.

#### render()

Render the inventory for terminal display.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### coact.analysis.back(agent)

Best-effort, **lossy** agent→skill extraction (harvest an agent into a skill).

Strips the persona/return-contract envelope down to a reusable skill stub
(name + description + a pointer to the skills it referenced). The actual
procedure usually lives in those referenced skills, so this cannot recover
it — the result is a starting point the user fleshes out, not a faithful
inverse of COMPLETE.

```pycon
>>> from coact import AgentDefinition
>>> sk = back(AgentDefinition(name='ux', description='Analyze.', skills=['ux', 'shared']))
>>> sk.meta.name
'ux'
>>> 'lossy' in sk.body.lower()
True
```

* **Return type:**
  `Skill`

### coact.analysis.diff(skill, agent)

Show what extras `agent` adds over its source `skill`.

`skill` is any skill source; `agent` is an `AgentDefinition`, an
agent `*.md` path, or a skill source (which is completed first).

```pycon
>>> from skill.base import Skill, SkillMeta
>>> s = Skill(meta=SkillMeta(name='ux', description='Analyze bundles.'), body='steps')
>>> from coact import complete
>>> d = diff(s, complete(s))
>>> any(f == 'prompt' and cls.startswith('extra') for f, cls, _ in d.rows)
True
```

* **Return type:**
  [`AgentDiff`](#coact.analysis.AgentDiff)

### coact.analysis.estimate(agents)

Surface the fan-out cost tradeoff for an agent set (DECISIONS D9).

```pycon
>>> from coact import AgentDefinition
>>> a = AgentDefinition(name='a', description='x', skills=['shared'])
>>> b = AgentDefinition(name='b', description='y', skills=['shared'])
>>> est = estimate([a, b])
>>> est.interdependent, est.shared_skills
(True, ['shared'])
```

* **Return type:**
  [`Estimate`](#coact.analysis.Estimate)

### coact.analysis.inventory(project=None)

Enumerate skills, derived agents, and MCP-exposed tools in a project.

```pycon
>>> import tempfile
>>> inv = inventory(tempfile.mkdtemp())
>>> inv.skills, inv.agents
([], [])
```

* **Return type:**
  [`Inventory`](#coact.analysis.Inventory)
