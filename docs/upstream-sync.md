# Upstream sync: kiwidude68/calibre_plugins

Dated windows. The reference clone lives at `~/.gitrepos/calibre_plugins`
(read-only by policy); each entry records the commit the ports track and
what the upstream window carried. Format follows the house's upstream-triage
idiom (see Viaduct's sync notes).

## 2026-11-23: initial window (clone at e14a679, "FictionDb - fix for threadsafe log")

- Clone created for Phase 21 (the CalibreQuarry plugin system lane).
- Ports pinned: extract_isbn **1.6.7** (CHANGELOG 2026-10-31; minimum
  calibre 2.0.0), find_duplicates **1.10.11** (CHANGELOG 2026-10-17;
  minimum calibre 2.0.0; config schema 1.7), quality_check **1.15.0**
  (CHANGELOG 2026-10-22; minimum calibre 3.48.0; config schema 1.9).
- Provenance note: chaley's `cbhaley/my_calibre_plugins` holds a returned
  "(old)" Quality Check fork (sat at 1.12.0) slated for deletion upstream;
  it is not a source of truth.
- `common/` imports across all three plugins are GUI-only (icons, menus,
  dialogs, widgets); no `common/` logic needs porting. Verified by the
  enumeration wave; per-plugin detail in `docs/crosswalk.md`.
