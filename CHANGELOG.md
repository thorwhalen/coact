# Changelog

All notable changes to this project are documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/);
each section corresponds to a git version tag (which is also the release
published to PyPI). Entries are commit subjects and PR titles, verbatim.

## [0.0.4] - 2026-06-05

- release: ship 0.0.4 (complete README CLI reference) [publish]
- harden: traversal-safe filesystem boundary + balanced JSON extraction ([#29](https://github.com/thorwhalen/coact/pull/29)) ([#30](https://github.com/thorwhalen/coact/pull/30))
- Harden coact: module split, host dry-run + fleet scaffold, deeper tests ([#28](https://github.com/thorwhalen/coact/pull/28))
- LiteLLM realization backend (provider-agnostic) ([#26](https://github.com/thorwhalen/coact/pull/26))
- Runnable end-to-end examples walkthrough ([#25](https://github.com/thorwhalen/coact/pull/25))

### Added

- feat(base): typed schema_ref resolution + opt-in live backend smoke tests ([#27](https://github.com/thorwhalen/coact/pull/27))
- feat(realize/sdk): D6 forced return_result tool fallback for return contract ([#21](https://github.com/thorwhalen/coact/pull/21))

### Fixed

- fix(realize/sdk): apply adversarial-review fixes to the merged D6 fallback ([#23](https://github.com/thorwhalen/coact/pull/23))

### Docs

- docs(cli): refresh __main__ docstring usage block to the full verb set (Closes [#31](https://github.com/thorwhalen/coact/pull/31)) ([#32](https://github.com/thorwhalen/coact/pull/32))
- docs(.claude): add repo agent toolkit — 4 skills + 2 agents ([#24](https://github.com/thorwhalen/coact/pull/24))

## [0.0.3] - 2026-06-04

- ci: gate PyPI publish behind [publish] marker (enabled=false) ([#20](https://github.com/thorwhalen/coact/pull/20))
- Fix 11 findings from the adversarial review pass ([#19](https://github.com/thorwhalen/coact/pull/19))
- Analysis utilities (diff/estimate/inventory/back) + argh CLI + layered README ([#18](https://github.com/thorwhalen/coact/pull/18))
- Synthesis LLM path (opt-in) + llm facade + mcp realize backend ([#17](https://github.com/thorwhalen/coact/pull/17))
- REALIZE: host + sdk backends behind an open-closed registry ([#16](https://github.com/thorwhalen/coact/pull/16))
- COMPLETE: skill → agent definition (mechanical, no-LLM) + policy + plan ([#15](https://github.com/thorwhalen/coact/pull/15))
- Foundation: AgentDefinition SSOT, emitters, coact: frontmatter, AgentStore ([#14](https://github.com/thorwhalen/coact/pull/14))
- 0.0.2:
- Update project description in README
- Initial commit
