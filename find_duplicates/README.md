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

Skeleton. The manifest (`cquarry-plugin.toml`) is the live contract; the
Phase 2 port lands the implementation. The parity ledger row lives in
`docs/crosswalk.md` at the repository root.
