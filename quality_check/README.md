# quality_check

A 1:1 port of kiwidude68's **Quality Check** calibre plugin for the
CalibreQuarry plugin system.

## Upstream provenance (attribution)

- Upstream repository: https://github.com/kiwidude68/calibre_plugins
- Upstream plugin folder: `quality_check`, version tracked: **1.15.0**
- Upstream author: kiwidude (Grant Drake); the Quality Check fork Charles
  Haley maintained was returned upstream and is not a source of truth
- Upstream license: GPL-3; this port is GPL-3 and carries the derivation
  forward (see `cquarry-plugin.toml` `[upstream]`).
- Derivation class: `port`

## What it does (parity contract)

A battery of checks over the library: cover size and dimensions, ePub
structure and style, MOBI/AZW EXTH checks, and metadata quality, plus the
saved-regex ePub content search and the fix actions (author formats, stored
sizes, MOBI ASIN/cdetype). Upstream's GUI idioms map to CLI twins: the check
results display becomes the audit report; the fixes become verbs behind the
host's write gates. The save-to-disk orphan cleanup stays declined on
upstream's own warning (never run against the calibre library itself).

## Status

Skeleton. The manifest (`cquarry-plugin.toml`) is the live contract; the
Phase 3 port lands the implementation. The parity ledger row lives in
`docs/crosswalk.md` at the repository root.
