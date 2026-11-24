# cquarry-plugins Roadmap

What's done, what's next. Updated as of v0.4.0.

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

- [x] The 1:1 scan contract: format preference order, first-hit-stops, PDF
      windows (first 10 pages, then last 5 in reverse), other-format file
      order (leading, trailing reversed, the rest), markup skipping, prefix
      validation with the extensible extension list, the three failure
      classes (identical / missing / none found). *(Shipped 0.2.0:
      extract_isbn/plugin.py, the single-file port with upstream's
      attribution carried; the recorded substitutions per the crosswalk:
      stdlib spine parsing for the EbookIterator, pdftotext + pdfinfo for
      pdftohtml + podofo, and the EbookIterator-only formats (mobi/azw3)
      report the deferral instead of scanning.)*
- [x] The write adoption surface: upstream's prompt-to-apply mapped to the
      host's dry-run/apply rails; per-book found / skip-identical /
      skip-conflict / write lines; changed-book ids pipe-ready. *(Shipped
      0.2.0: the scan verb; a stored DIFFERENT isbn is the reviewer-visible
      CONFLICT class, never auto-overwritten, the host's recorded policy;
      --apply rides the WriteGate, whose label-pair fix raised this
      plugin's calibrequarry floor to >=3.94.1.)*
- [x] Behavior tests per the host's conventions; the host's end-to-end
      approval drill (verify, approve, dry run, apply, re-hash refusal) is
      the deliverable this port proves. *(Shipped 0.2.0:
      tests/test_extract_isbn.py's 26 tests: scanner units, the spine and
      PDF windows (mocked plus real poppler over crafted 20-page PDFs),
      the scratch-library verb end to end (conflict / same / write /
      no-format classes; the dry run writes nothing and --apply reads
      back), and the host verify pass with the manifest probe.)*

## Phase 2: the find_duplicates port

- [x] The matcher ladder per field (Identical, Similar, Soundex with the
      adjustable length, Fuzzy, Ignore), Binary Compare, Identifier compare.
      *(Shipped 0.3.0: find_duplicates/plugin.py, the single-file port with
      upstream's attribution; the ladder regexes, strip lists, reversal
      hashes, and the soundex port carried verbatim; the recorded
      substitutions: the NFKD-strip for calibre's get_udc() and the sha
      cache in the plugin config instead of the library database.)*
- [x] Groups and the report surface (JSON in upstream's export shape plus
      the text report, the recorded replacement for the GUI's
      marked:duplicates highlighting); the cross-library mode
      (`search --against PATH`, report-only, no exemptions, upstream's
      rule). *(Shipped 0.3.0; the grouping pipeline runs the upstream
      partition verbatim including the don't-repartition subtlety.)*
- [x] Exemptions (per-library, host config storage) and the option surface.
      *(Shipped 0.3.0: `exempt --books/--authors` records upstream's
      bookExemptions/authorExemptions schema per library in the plugin's
      config dir (contract 2), keyed by the absolute library path -- the
      recorded storage substitution, the GUI plugin's and this plugin's
      exemption sets independent; `--list/--remove/--clear` manage them.)*
- [x] The actions behind the host's gates: merge, binary-duplicate format
      removal, row deletion, bulk metadata rename, and the variations
      reports (whose tags-soundex length correction rides along). *(Shipped
      0.4.0 on host 3.95.1's action seams + 3.95.2's plan seam (contract 3):
      merge copies the source formats into the keeper's directory and
      registers them in the same one-batch transaction that fills/unions the
      chosen fields and removes the absorbed rows -- the plan prints under
      --apply too, so a CONFLICT identifier line is never invisible;
      remove-duplicate-formats keeps the earliest-mtime copy per sha;
      delete is upstream's Delete key; variations reports the field
      clusters and rename rides cquarry's own rename_entity through the
      gate. The tests drive every action over scratch libraries with REAL
      format files and resolve keeper paths through the engine, because the
      author re-lay renames the keeper's files after an authors change.)*

## Phase 3: the quality_check port

- [x] The check families: cover size/dimensions; ePub structure; ePub style;
      MOBI/AZW (EBOK cdetype, ASIN, EXTH sharing, clipping); metadata
      quality; per-check exclusions. *(Shipped 0.5.0 as a multi-file package
      riding host 3.96.0's package loader: the metadata/missing/covers/MOBI
      families in checks_db.py, the ePub structure/style battery in
      checks_epub.py, the EXTH reader in mobi_exth.py, titlecase ported
      separately with attribution. Deferred with recorded reasons: the
      stored-size repair's fix verb (the host seam exists since 3.95.1;
      wired in the v0.6.0 fix batch) and the MOBI ASIN/cdetype repair
      (needs a MOBI writer). The css_margins prefs comparison is the
      recorded substitution: flag-only for now.)*
- [x] The saved-regex ePub content search (part of the port; parity is the
      directive). *(Shipped 0.5.0 as the search-epub verb: upstream's
      scopes (html/plaintext/css/opf/ncx/zip), ignore-case, all-matches,
      and the does-not-contain flag.)*
- [x] The fixes behind the host's gates: author swap/reorder, initials
      format, ascii rename, stored-size repair, MOBI ASIN/cdetype repair.
      The save-to-disk orphan cleanup stays declined on upstream's own
      warning. *(Partially shipped 0.5.0: author swap, initials format,
      ascii rename, author/title sort recomputation -- all through the
      WriteGate. Deferred to the v0.6.0 fix batch with recorded reasons:
      stored-size repair (seam exists, verb pending) and the MOBI
      ASIN/cdetype repair (needs a stdlib MOBI writer). The save-to-disk
      cleanup stays declined.)*
