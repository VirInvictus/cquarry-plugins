# find_duplicates

A 1:1 port of kiwidude68's **Find Duplicates** calibre plugin for the
CalibreQuarry plugin system.

## Upstream provenance (attribution)

- Upstream repository: https://github.com/kiwidude68/calibre_plugins
- Upstream plugin folder: `find_duplicates`, version tracked: **1.10.11**
- Upstream author: kiwidude (Grant Drake)
- Upstream license: GPL-3; this port is GPL-3 and carries the derivation
  forward (see `cquarry-plugin.toml` `[upstream]`).
- Derivation class: `port`

## What it does (parity contract)

Finds duplicate books across three search types (title/author compare over
the per-field matcher ladder, byte-identical format compare, identifier
compare), forms groups, and reports them. Upstream's GUI idioms map to CLI
twins: the marked-book highlighting becomes the group report; the merge
action, which upstream delegates to calibre's GUI merge, is implemented
directly behind the host's write gates (the recorded parity extension);
exemptions persist in the host's config keyed per library, where upstream
uses the library database's namespaced preferences.

## Status

Implemented (Phase 2, the read half). Verbs: `search` (the three search
types with the per-field matcher ladder carried verbatim; groups render
as the report or `--format json` in upstream's export shape) and `exempt`
(--books/--authors record not-duplicate sets per library in this plugin's
config, --list/--remove/--clear manage them). Cross-library comparison:
`search --against /path/to/other/metadata.db` (report-only, no
exemptions, upstream's rule). The actions half (merge, binary-format
removal, row deletion, bulk rename, the variations reports) is the
recorded Phase 2 actions box; its roadmap row tracks it. The parity
ledger rows live in `docs/crosswalk.md`.
