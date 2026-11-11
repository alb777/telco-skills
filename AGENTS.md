# Working context

Public repo of Agent Skills for mobile core signalling troubleshooting, at v0.3.0. It ships one skill, `telcode`: an offline Python CLI that looks up Diameter, 5G/4G NAS, 5G SBA, GTPv2-C, PFCP, MAP, SCCP, Q.850 and SIP codes with their spec references, splits IMSIs and decodes TBCD.

## Layout

1. `skills/telcode/SKILL.md` is the skill: frontmatter (`name`, `description`, `metadata.version`) plus the instructions the agent follows. The `description` decides when an agent loads the skill, so it names troubleshooting questions, not only lookups.
2. `skills/telcode/scripts/telcode.py` is the whole CLI, Python 3.10+, standard library only.
3. `skills/telcode/assets/codes/*.json` holds one table per file, with `family` equal to the file stem. `assets/notes.json` holds hand-written notes keyed by table and code.
4. `tests/test_telcode.py` loads the script by path and calls `main()`. Plain unittest, no pytest.
5. `tools/update_data.py` regenerates the IANA and 3GPP tables. `tools/record_demo.py` records `docs/demo.gif` from real runs.
6. `.claude-plugin/marketplace.json` makes the repo a Claude Code plugin marketplace. CI (`.github/workflows/ci.yml`) runs the tests on Python 3.10 and 3.14 plus a lint job.
7. This repo is public and intentionally has no autonomous agent team: no ops role, no scheduled run, no agent workflow. Code work here is by hand or from a manual run someone starts on purpose.

## Commands

Verified 2026-10-17, from the repo root. The tool versions are the ones CI pins; the README's unpinned `uvx ruff` can drift.

1. `python3 -m unittest discover -s tests`: 34 tests, OK.
2. `uvx ruff@0.17.0 check .` and `uvx ruff@0.17.0 format --check .`: clean.
3. `uvx mypy@2.4.0`: strict mode over the script, tools and tests, no issues.
4. `uvx --from skills-ref@0.1.1 agentskills validate skills/telcode`: valid skill.
5. `python3 skills/telcode/scripts/telcode.py 5001 --json`: two matches, `"ambiguous": true`. Exit codes are 0 found, 1 nothing found, 2 bad input.

Not run (they rewrite files or publish):

1. `python3 tools/update_data.py`: downloads the sources and rewrites the JSON tables. Read the diff before committing.
2. `python3 tools/record_demo.py`: needs `agg` and `claude` on PATH. `agg` is often missing; install it first.
3. Release: bump `metadata.version` in SKILL.md, commit, `git push origin main`, then `gh run list --commit <sha>` until both CI jobs are green.

## Conventions

1. One-line conventional commits without scope: `feat: x`, `fix: x`, `docs: x`, `ci: x`, `chore: x`. No body, no AI attribution, no Co-Authored-By.
2. Solo repo: commit straight to `main`, no PRs, no force-push.
3. The version lives only in `metadata.version` in SKILL.md and is bumped inside the `feat:` commit that ships the feature. There are no git tags and no GitHub releases.
4. A new table lands in one `feat:` commit: the JSON, its parser in `update_data.py` (or a hand-kept file), `TABLE_ORDER` in telcode.py, tests, SKILL.md (table picker, description, Not covered), README (usage, Data, Not covered) and the marketplace.json description and keywords.
5. When the demo story changes, re-record the GIF in its own `docs:` commit.
6. Data comes only from public IANA, 3GPP and ITU-T publications. Never add operator-internal names, configs, traces or real subscriber data.
7. Cite upstream issues, PRs and specs with the full https URL, never a bare `#1234` or `owner/repo#1234`.

## Gotchas

1. Codes collide across tables (5001 is two Diameter codes, 27 is MAP and Q.850). Showing every match is the feature; never collapse a lookup to one table unless `--table` says so.
2. Names stay exactly as the sources spell them, typos included. Do not "fix" them.
3. Tables are discovered by globbing `assets/codes/`. `TABLE_ORDER` only sets display order; a missing entry sorts last instead of failing.
4. The Q.850 and SCCP tables and `notes.json` are hand-maintained. `update_data.py` never writes them.
5. 3GPP's FTP answers 403 to the default urllib user agent, hence the custom `USER_AGENT` in `update_data.py`.
6. A 5G SBA cause name is unique only within one service API, so `sba-cause` keeps one entry per wording and is looked up by name, in any case.
7. `record_demo.py` refuses to record when the headless Claude session did not use the skill. Never hand-edit the GIF.
8. No dependencies, ever: the script must stay auditable and run without an install step. CI tests on 3.10, so no 3.11+ syntax or stdlib modules.
9. CI actions are on their Node 24 releases (`checkout`, `setup-python`, `setup-uv` at v7). Keep them there when bumping.
10. `ruff format --check .` also picks up the Markdown files (README, SKILL.md, AGENTS.md) and checks their Python code blocks, so a `python` block in docs has to be ruff-formatted too.
