# extract_isbn

A 1:1 port of kiwidude68's **Extract ISBN** calibre plugin for the
CalibreQuarry plugin system.

## Upstream provenance (attribution)

- Upstream repository: https://github.com/kiwidude68/calibre_plugins
- Upstream plugin folder: `extract_isbn`, version tracked: **1.6.7**
- Upstream author: kiwidude (Grant Drake)
- Upstream license: GPL-3; this port is GPL-3 and carries the derivation
  forward (see `cquarry-plugin.toml` `[upstream]`).
- Derivation class: `port`

## What it does (parity contract)

Scans a book's own text for printed ISBNs and adopts the found value into the
library metadata. Upstream's GUI idioms map to CLI twins: the prompt-to-apply
flow becomes the host's dry-run/apply rails; the failure dialog becomes the
per-book report (identical stored / missing stored / none found).

## Status

Skeleton. The manifest (`cquarry-plugin.toml`) is the live contract; the
Phase 1 port lands the implementation. The parity ledger row lives in
`docs/crosswalk.md` at the repository root.
