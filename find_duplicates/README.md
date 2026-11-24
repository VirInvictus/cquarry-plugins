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

Implemented (Phase 2 complete). Read verbs: `search` (the three search
types with the per-field matcher ladder carried verbatim; groups render
as the report or `--format json` in upstream's export shape), `exempt`
(--books/--authors record not-duplicate sets per library in this plugin's
config, --list/--remove/--clear manage them), `variations` (the field
clusters per matcher), and cross-library comparison via `search --against
/path/to/other/metadata.db` (report-only, no exemptions, upstream's
rule). Action verbs, dry-run by default and `--apply` behind the host's
gates: `merge --keeper ID --ids ID,ID [--fields ...]` (calibre's merge:
formats copied into the keeper, chosen fields fill/union, absorbed rows
removed; a conflicting identifier is reviewer-visible and never
overwritten), `remove-duplicate-formats --ids` (keep the earliest-mtime
copy of each byte-identical format), `delete --ids` (upstream's Delete
key), and `rename --kind --from --to` (the entity rename behind the
variations report). The parity ledger rows live in `docs/crosswalk.md`.
