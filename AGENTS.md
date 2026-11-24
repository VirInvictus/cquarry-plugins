# AGENTS.md (cquarry-plugins)

Per-project guidance. Overrides the global file where they conflict.

## What this is

The GPL-3 plugins monorepo for the CalibreQuarry plugin system: 1:1 ports of
kiwidude68's Quality Check, Extract ISBN, and Find Duplicates. The host is
MIT (`~/.gitrepos/CalibreQuarry`, Phase 21 of its roadmap); the licensing
compromise and the lane rules are recorded in that roadmap and in this repo's
spec.md. **The import boundary is one-way: this repo's code may import the
host's public APIs at runtime through the host; the MIT repositories never
import from here. No GPL bytes enter the MIT repos.**

## Upstream

- Reference clone: `~/.gitrepos/calibre_plugins` (kiwidude68/calibre_plugins,
  HEAD e14a679 as of 2026-11-23). READ-ONLY by policy; never edit it, never
  run anything in it. Sync windows: `docs/upstream-sync.md`.
- Pinned ports: extract_isbn 1.6.7, find_duplicates 1.10.11, quality_check
  1.15.0.
- chaley's `cbhaley/my_calibre_plugins` is NOT a source of truth: it holds
  only a returned "(old)" Quality Check fork slated for deletion upstream.

## Lane rules

- **1:1 parity** is the directive: every crosswalk row ports; GUI idioms map
  to named CLI twins (prompt-to-apply becomes dry-run/apply, failure dialogs
  become reports, marked-highlighting becomes the report, background jobs
  become foreground verbs); a GUI capability with no CLI twin is recorded in
  `docs/crosswalk.md` as the recorded deviation, never silently dropped.
- The host enforces the trust boundary (approval harness, capability gates,
  write rails, version floors). These plugins declare honestly and never try
  to route around the host's seams.
- Floors (`requires.cquarry`, `requires.calibrequarry`) are re-pinned in the
  same commit that starts using the newer surface. The lint suite validates
  structure, never values.
- stdlib-only: no third-party dependencies. The plugins load into the host
  without pip.

## Tooling

- Python >= 3.14, stdlib only. Format and lint with ruff (pinned `0.15.20`,
  the CI version; local runs gate with `uvx ruff@0.15.20`).
- Tests: `python3 -m unittest discover -s tests` from the repo root. The
  manifest lint loads TOML by path (tomllib); it never imports plugin code.
- Version carriers move together: `VERSION` == pyproject `project.version` ==
  the newest `## vX.Y.Z` heading in patchnotes.md (`tests/test_version.py`).
- Each plugin's manifest version is that plugin's own lineage; the repo
  VERSION is tooling only.

## Conventions

- Prose: no em-dashes anywhere a human reads.
- Manifest changes are spec changes: spec.md's manifest table and the lint
  suite move in the same commit.
- `docs/crosswalk.md` is the parity ledger: a check lands in code only after
  it has a row there.
