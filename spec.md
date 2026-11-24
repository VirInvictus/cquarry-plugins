# cquarry-plugins spec

The contract. Read before changing semantics.

## Purpose

This repository holds the GPL-3 plugins for the CalibreQuarry plugin system.
The three proof-of-concept plugins are 1:1 ports of the same-named plugins from
kiwidude68/calibre_plugins (Quality Check, Extract ISBN, Find Duplicates):
each reproduces its upstream plugin's functional contract exactly, with GUI
idioms mapped to named CLI twins. The CalibreQuarry host is MIT and lives in a
separate repository; the import boundary is one-way (plugins depend on the
host API; the host never imports from this repository), so the MIT license of
the host and the GPL-3 license of these plugins coexist cleanly.

## Semantics

### The manifest contract

Every plugin declares itself in a `cquarry-plugin.toml` at its package root:

| Field | Meaning |
|---|---|
| `schema` | Manifest schema version; the host refuses values it does not know, fail-closed. |
| `name` | Plugin name; must equal the directory name. Unique across a source. |
| `version` | The plugin's own SemVer, independent of this repository's VERSION. |
| `api_version` | The host plugin-API contract the plugin targets (integer). |
| `license` | SPDX expression; `GPL-3.0-only` for every plugin in this repo. |
| `capabilities` | Subset of `read`, `write`, `network`. `read` is the floor; `write` requires the host's approval harness; `network` is declared and every fetch is logged by the host. |
| `entry` | `module:function` registration hook the host imports and calls. |
| `description` | One human line. |

### The version floors (fail-closed)

`[requires]` carries two explicit dependency floors, never inherited or
defaulted:

- `requires.cquarry`: the minimum supported cquarry engine. The host judges
  this against the engine the process actually imported (its `__version__`),
  never against distribution metadata, which can lag a checkout.
- `requires.calibrequarry`: the minimum supported host.

All three version gates (`schema`/`api_version` plus the two floors) are
checked by the host at install, update, and load, naming the version found,
the floor required, and the fix. In this repository, the floors are declared
honestly and re-pinned when the releases they name actually cut; the lint
suite validates structure, not specific values.

### Source discovery

A directory containing a `cquarry-plugin.toml` at its root is a plugin. A
repository holding one such manifest is a single-plugin source; a repository
holding several (one per plugin directory, this repository's shape) is a
multi-plugin source. Detection is by discovery; no configuration names which.

### Attribution

Every plugin derived from upstream carries, in its README: the upstream
repository and plugin folder, the upstream version this port tracks, the
upstream license, and the derivation class (`port` for code derived from
upstream GPL-3, `clean-room` for reimplementations, `original` for
new plugins). The repository's LICENSE is GPL-3.0-only and covers every
plugin; no GPL code enters the MIT host repositories, ever.

### Versions

`VERSION` at the repository root is the tooling version (CI, release
tooling); it moves with `pyproject.toml` and the newest patchnotes heading
(`tests/test_version.py` pins all three). Each plugin's manifest version is
that plugin's own lineage.

### Upstream sync

`docs/upstream-sync.md` carries dated entries recording which upstream commit
this repository's ports track and what changed in each upstream window. The
GPL obligation runs both ways: carrying upstream changes cleanly, or
recording the divergence here.

## Non-goals

- No host code: the plugin system itself lives in CalibreQuarry.
- No pip packaging: plugins are git-sourced directories loaded by manifest.
- No GUI: every surface is CLI-shaped by design.
