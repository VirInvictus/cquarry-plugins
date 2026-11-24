# cquarry-plugins Roadmap

What's done, what's next. Updated as of v0.1.0.

The lane this repository serves is Phase 21 of CalibreQuarry's roadmap (the
CQ plugin system lane). The host ships first; these plugins prove it. Ship
order: extract_isbn, then find_duplicates, then quality_check.

## Phase 0: skeleton

- [x] Repository scaffold: house layout, GPL-3 LICENSE, placeholder logo,
      single-source VERSION synced to pyproject and patchnotes.
- [x] The three plugin packages with valid `cquarry-plugin.toml` manifests
      (capabilities, api_version, both version floors, upstream provenance).
- [x] The manifest lint suite (`tests/test_manifests.py`) and the version-sync
      pin (`tests/test_version.py`).
- [x] CI (house-hardened shape: SHA-pinned actions, permissions, concurrency,
      timeout, pinned ruff).
- [x] `docs/upstream-sync.md` seeded with the clone window.
- [x] `docs/crosswalk.md`: the parity ledger over the three upstream surfaces
      (every check, matcher, option, and fix disposed as ported / substituted
      / extension / declined with its CLI twin named; the enumeration wave ran
      2026-11-23 over the e14a679 clone).

## Phase 1: the extract_isbn port

- [ ] The 1:1 scan contract: format preference order, first-hit-stops, PDF
      windows (first 10 pages, then last 5 in reverse), other-format file
      order (leading, trailing reversed, the rest), markup skipping, prefix
      validation with the extensible extension list, the three failure
      classes (identical / missing / none found).
- [ ] The write adoption surface: upstream's prompt-to-apply mapped to the
      host's dry-run/apply rails; per-book found / skip-identical /
      skip-conflict / write lines; changed-book ids pipe-ready.
- [ ] Behavior tests per the host's conventions; the host's end-to-end
      approval drill (verify, approve, dry run, apply, re-hash refusal) is
      the deliverable this port proves.

## Phase 2: the find_duplicates port

- [ ] The matcher ladder per field (Identical, Similar, Soundex with the
      adjustable length, Fuzzy, Ignore), Binary Compare, Identifier compare.
- [ ] Groups and the report surface (CSV/JSON + id lists); the cross-library
      mode.
- [ ] Exemptions (per-library, host config storage) and the option surface.
- [ ] The actions behind the host's gates: merge, binary-duplicate format
      removal, row deletion, bulk metadata rename.

## Phase 3: the quality_check port

- [ ] The check families: cover size/dimensions; ePub structure; ePub style;
      MOBI/AZW (EBOK cdetype, ASIN, EXTH sharing, clipping); metadata
      quality; per-check exclusions.
- [ ] The saved-regex ePub content search (part of the port; parity is the
      directive).
- [ ] The fixes behind the host's gates: author swap/reorder, initials
      format, ascii rename, stored-size repair, MOBI ASIN/cdetype repair.
      The save-to-disk orphan cleanup stays declined on upstream's own
      warning.
