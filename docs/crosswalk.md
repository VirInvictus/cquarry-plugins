# The parity crosswalk (the 1:1 ledger)

What every upstream surface item becomes in this repository. Row dispositions:

- **ported**: carried into the CQ plugin, CLI twin named.
- **substituted**: upstream's calibre-internal mechanism replaced by an
  equivalent the host provides; behavior unchanged.
- **extension**: a CLI capability upstream delegates to the GUI; implemented
  here behind the host's gates.
- **declined**: with the recorded reason. A deviation without a twin is
  recorded, never silent.

Sources: the enumeration wave over `~/.gitrepos/calibre_plugins` at `e14a679`
(extract_isbn 1.6.7, find_duplicates 1.10.11, quality_check 1.15.0); path
cites are upstream files. A check lands in code only after it has a row here.

## Conventions carried across all three ports

- Upstream's marked-ids mechanism (`db.set_marked_ids` + `marked:<text>`
  searches) becomes the plugin's report: id lists (CSV/JSON, pipe-ready).
  This is the standing CLI twin for every check's result surface.
- Scope: upstream iterates the GUI's current view or selection. The CLI
  default is the whole library; explicit target arguments (`--ids`,
  `--search`) narrow it. Fixes that are selection-only upstream require an
  explicit target in the port (recorded per row).
- Progress dialogs become plain iteration with per-book log lines;
  error/info dialogs become stderr and the host's exit 0/1/2 contract.
- Confirmation dialogs become the host's dry-run default plus `--apply`
  (upstream's `askForConfirmation: True` default matches the house rail).
- `common/` imports are GUI-only in all three plugins (icons, menus, dialogs,
  widgets; verified per plugin); zero logic ports from `common/`.
- Upstream gates some features on the running calibre version (quality_check:
  size repair needs calibre >= 5.9's API, notes normalization >= 7.0). The
  port's floors are declared in the manifest and judged by the HOST; plugin
  code never probes calibre.

## extract_isbn 1.6.7 (upstream `extract_isbn/`)

| Upstream surface | Disposition | CLI twin / notes |
|---|---|---|
| Scan driver: in-process thread (<= `workerThreshold` books) vs queued out-of-process batches (`jobs.py:30-203`) | substituted (partial) | One sequential foreground verb over the target set. `workerThreshold`/`batchSize` are GUI job-queue cancel-safety and are **declined** (recorded). |
| Format preference order (`sort_formats_by_preference` over calibre's `input_format_order`, EPUB first, PDF near-last) | ported | The order list carried as plugin config; unknown formats last. |
| PDF page-count via podofo with `pdfinfo` fallback (`pdf.py:94-157`) | substituted | Page count via poppler (`pdfinfo`); single tool, no podofo. |
| PDF windows: 10 front + 5 back, one whole-document pass at <= 15 pages (`pdf.py:23-24, 77-86`) | ported | Windows carried exactly; extraction via `pdftotext` (the host's poppler seam) instead of `pdftohtml -xml`. |
| `< 100` bytes of extracted text reads as DRM (`pdf.py:229-230`) | ported | An empty/near-empty extraction is the decline class; the DRM naming becomes the row error. |
| Non-PDF spine windows `EPUB_FILE_SCANS` `((15,10,-5),(10,6,-4),(6,4,-2),(3,2,-1),(2,1,-1),(1,1,0))`, front forward / rear reversed / middle forward, stop on first hit (`nonpdf.py:17-22, 63-78`) | ported | Table carried verbatim; spine iteration via stdlib zip + OPF parsing through the host's file resolver instead of calibre's `EbookIterator`. |
| Markup skipping + scan regex (`scan.py:17-20`: style blocks deleted, tags to `!`, the 9-22 char window ending in digit/x) | ported | Verbatim (pure logic). |
| Cleanup: `-10 `/`-13 ` 4-char prefix strip, non-`[0-9X]` strip, all-identical-digit rejection (`scan.py:65-90`) | ported | Verbatim. |
| Validation: ISBN-10 checksum unrestricted; ISBN-13 prefix gate (default `977/978/979`, comma-extended) then checksum; first ISBN-13 else first ISBN-10 (`scan.py:32-37`, calibre `check_isbn`) | ported | Checksum via the mod-11 / mod-10 formulas ported locally (stdlib, no calibre import); prefix list as config. |
| Classification: extracted / same-isbn / failed / no-format (`jobs.py:83-92, 101-131`) | ported | The four classes and the detail-line format carried into the report. |
| Write: bulk `set_field('identifiers', ...)`, key `isbn`, identical-skip (`action.py:160-177`) | ported | Through the host WriteGate (`set_identifier` seams); identical-skip policy carried. |
| Staleness re-check before apply (`action.py:132-159`) | substituted | The host's read-back verify owns this class; the plan names the snapshot. |
| `proceed_question` apply prompt + "Some books changed" warning | substituted | The dry run IS the prompt; `--apply` proceeds; changed-since-plan rows re-evaluated at apply. |
| `postTask` `marked:isbn_updated` search | ported | The report carries the changed-book ids, pipe-ready (the recorded twin). |
| `displayFailures` failure dialog | ported | Failures always in the report; the exit contract carries the signal (no dialog toggle). |
| Config: `validISBN13Prefix`, `postTask`, `workerThreshold`, `batchSize`, `displayFailures`, `askForConfirmation` (`config.py:32-56`) | ported / declined | `validISBN13Prefix` and the report shape port; `askForConfirmation` = the host dry-run default; `workerThreshold`/`batchSize` declined (GUI cancel-safety); `displayFailures` declined (report is unconditional). |

## find_duplicates 1.10.11 (upstream `find_duplicates/`)

| Upstream surface | Disposition | CLI twin / notes |
|---|---|---|
| Search types `titleauthor` / `binary` / `identifier` (legacy `'isbn'` value migrates) (`dialogs.py:49, 287-288`; `book_algorithms.py:414-435`) | ported | Three search modes; the legacy `isbn` spelling accepted as an alias for `identifier`. |
| TitleAuthor grouping: `title_hash + author_hash` with the reversed-order author hash second entry; languages option prefixes the title hash; title-`ignore` becomes author-only grouping (`book_algorithms.py:333-406`; `matching.py:175-205`) | ported | Verbatim semantics, including the reversal entry and the language participation option. |
| Binary compare: group by exact size, then SHA per (book, fmt); per-book mtime-keyed hash cache in plugin book data (`book_algorithms.py:251-330`) | ported | Same two passes; the cache becomes a plugin-side cache keyed by (path, mtime, size) in the host's cache area, not the calibre DB. |
| Identifier compare: user-chosen type from the library's identifier types, exact string equality, default `isbn` (`book_algorithms.py:212-248`) | ported | Carried, no normalization (the exact-equality semantics are the point). |
| Grouping pipeline: shrink < 2, subset-clean, sort by title/count, exemption partition, multi-group membership (`book_algorithms.py:45-69, 96-161, 163-209`) | ported | Verbatim pipeline. |
| Soundex: Knuth/Jorgensen variant, first-letter kept, zero-stripped, per-field lengths (title 6, author 8, publisher 6, series 6, tags 4) (`matching.py:96-128, 11-72`) | ported (corrected) | Upstream quirk recorded: the tags matcher actually reads the PUBLISHER length (`matching.py:406`). The port wires `tagsSoundexLength` honestly; the quirk is the recorded deliberate correction. |
| Title ladder strips: identical (lower), similar (automerge strip: punctuation/article/`[-._]`/whitespace), soundex, fuzzy (subtitle drop, edition-paren tokens, `and/&/or/aka` tail drop, `a`/`the` token drop, no-separator join) (`matching.py:81-94, 135-205`) | ported | Verbatim strip lists. |
| Author ladder: identical; similar (initials dropped, space-joined, rotation reversal); soundex (surname-fronted, length 8, reversal = original order); fuzzy (`F` + surname); ignore-word list `von van jr sr i ii iii second third md phd`; apostrophes kept (`matching.py:216-282`) | ported | Verbatim, including the reversal hashes. |
| Series/publisher/tags ladders with their drop lists (`matching.py:289-413`) | ported | Verbatim. |
| Variations reports (authors/series/publisher/tags over similar/soundex/fuzzy) + bulk rename via `db.rename_*` (`variation_algorithms.py:25-138`; `dialogs.py:618-1034`) | ported | The variation report; rename through the WriteGate as a gated bulk-rename verb. The session-only "Ignore" button becomes a declined row (upstream does not persist it either; recorded). |
| Merge: **not implemented upstream**; delegated to calibre's GUI merge, the plugin only prunes dead ids afterward (`duplicates.py:634-690`) | extension | The port implements merge semantics behind the WriteGate (move formats into the kept row, chosen metadata merge, remove absorbed rows) because there is no GUI to delegate to; the recorded parity extension. |
| Row deletion: not implemented upstream (the GUI Delete key) | extension | Gated delete verb, same class as merge; dry-run default names every removal. |
| Binary-format auto-removal: keep the earliest-timestamp copy, `remove_format` the same-size same-sha rest (`duplicates.py:762-788`) | ported | Behind the WriteGate; `autoDeleteBinaryDups` default False carried. |
| Mark-as-exempt (group or all remaining) with confirmations (`duplicates.py:374-425`) | ported | An exempt verb; no confirmation dialog (the dry run is the review). |
| Exemption persistence: per-library `db.prefs` namespaced `FindDuplicatesPlugin/settings` (`bookExemptions`, `authorExemptions`, schema 1.7; legacy global-JSON migration) (`config.py:23-123`) | substituted | Host persistent config keyed per library. Upstream stores INSIDE the library DB; the CQ store is separate, so GUI-plugin and CQ-plugin exemption sets are independent (the recorded coexistence answer: they do not co-mingle). |
| Cross-library mode: read-only second db, exemptions NOT applied, three comparison paths (author / binary / title-identifier), `marked:library_duplicate` surfacing, save-log (`duplicates.py:791-1110`) | ported | Second root opened read-only through the host read API; report-only (the mark becomes report output); the log save becomes the report file. |
| Export groups JSON (`books_for_group`, `entangled_groups_for_book`, library uuid/path, timestamp) (`action.py:332-367`) | ported | The JSON report carries the same field set. |
| Group navigation: skip/next/previous, highlight, one-at-a-time restriction, tag-browser author boxing, sort-history (`duplicates.py:692-758`) | declined | Pure GUI navigation; the report replaces it (recorded). |
| Config keys: `searchType`, `identifierType`, `titleMatch`, `authorMatch`, soundex lengths x5, `includeLanguages`, `autoDeleteBinaryDups` | ported | Verb options with the same defaults. |
| Config keys: `showAllGroups`, `sortGroupsByTitle`, `showTagAuthor`, `showVariationBooks`, `displayLibraryResults` | declined | Pure display idioms with no CLI twin (recorded). |

## quality_check 1.15.0 (upstream `quality_check/`)

Framework: `BaseCheck.check_all_files` iterates books, drops per-check
exclusions, collects verdicts, surfaces via marked ids (`check_base.py:41-84`).
The ported framework is the same loop with the report as the surface.

### Cover checks (1)

| Check / menu key | Disposition | Notes |
|---|---|---|
| `check_covers`: four modes (no cover; size < / > N KB; dimensions comparisons with 0-as-wildcard; aspect-ratio band +/- tolerance%) (`check_covers.py:24-147`) | ported | Modes become flags; PIL's `Image.open` becomes a stdlib IHDR/JPEG-header read (the host's cover-audit precedent) or a declared fallback. `cover:False` mode runs the engine search (row below). |

### Missing-data checks (11; all are literally saved searches, non-excludable)

| Check | Disposition | Notes |
|---|---|---|
| `check_missing_title/author/isbn/pubdate/publisher/tags/rating/comments/languages/cover/formats` (`check_missing.py:19-41`) | ported | Each carries its exact search expression (`title:"=Unknown"`, `isbn:False`, ...) executed through the host's search API (substituted: `db.search` instead of the GUI search box). |

### MOBI/AZW checks (4)

| Check | Disposition | Notes |
|---|---|---|
| `check_mobi_missing_ebok` (EXTH 501 != EBOK) | ported | EXTH reads via a stdlib MOBI/EXTH parser (upstream's `mobi6.py` reads depend on calibre internals only for the UPDATER half; the reader logic ports). |
| `check_mobi_missing_asin` (EXTH 113 empty) | ported | Same parser. |
| `check_mobi_share_disabled` (EXTH 113 vs 504 mismatch; MOBI only) | ported | Carried. |
| `check_mobi_clipping_limit` (EXTH 401 < 100) | ported | Carried. |

### Metadata checks (19)

| Check | Disposition | Notes |
|---|---|---|
| `check_title_sort` / `check_author_sort` (stored vs computed) | ported | Sort computation via the host (cquarry's author-sort and title-sort semantics are the engine's own). |
| `check_isbn` (checksum fails) | ported | The ported checksum formulas. |
| `check_pubdate` (== import timestamp default) | ported | Carried. |
| `check_dup_isbn` / `check_dup_series` (grouping > 1) | ported | Carried. |
| `check_series_gaps` (missing integers in 1..max-1; max >= 1000 skipped) | ported | Carried. |
| `check_series_pubdate` (index-ascending vs pubdate; index < 1 = anthologies ignored) | ported | Carried. |
| `check_excess_tags` (unique count minus exclusions > `maxTags` default 5) | ported | Config carried. |
| `check_html_comments` / `check_no_html_comments` (closing-tag patterns) | ported (corrected) | Upstream bug recorded: a missing comma concatenates `</div>` + `</p>` into one pattern (`check_metadata.py:393-394`). The port carries the intended list; the bug is the recorded deliberate correction. |
| `check_authors_commas` / `check_authors_no_commas` / `check_authors_case` | ported | Carried. |
| `check_authors_non_alpha` (post-unidecode `[^A-Za-z'.,\- ]`) / `check_authors_non_ascii` (unidecode != raw) | substituted | Unidecode has no stdlib twin; the port carries a small NFKD-strip approximation and the row records the substitution (a non-ascii author the approximation folds differently is a possible false negative; noted). |
| `check_authors_initials` (formatted initials != author, mode from config) | ported | The four modes (`A.B.`, `A. B.`, `A B`, `AB`) and the ignore-token list carried (`helpers.py:7-76`). |
| `check_titles_series` (title contains `-` or starts with a digit) | ported | Carried. |
| `check_title_case` (titlecase comparison) | ported | calibre's `titlecase` algorithm ported locally (small, pure). |

### ePub checks (31 menu keys / 27 methods + search)

All ported unless noted; the shared machinery carries verbatim: the
manifest-worthy filter (`mimetype`, META-INF, `.opf`, pagemap, display-options
skipped), the DRM skip (any non-Adobe-RC `encryption.xml` algorithm skips the
check with a named reason), the file-class lists, and stdlib zip/XML parsing
(upstream already uses stdlib here; no calibre internals in the check path).

| Group | Checks | Notes |
|---|---|---|
| Jacket | `check_epub_jacket` (+ `no` / `legacy` / `multiple`) | Current `<meta content="jacket" name="calibre-content">` and legacy `calibrerescale` markers carried. |
| Structure | `no_container`, `namespaces`, `non_dc_metadata` (dcterms:modified exempt), `opf_files_missing`, `unmanifested_files` (iTunes/bookmark/OS artifacts tolerated), `unused_css_files`, `unused_images`, `broken_image_links`, `itunes`, `bookmark`, `os_artifacts`, `inside_epub`, `corrupt_zip` | Carried; regexes and tolerances verbatim. |
| TOC | `toc_hierarchical`, `toc_size` (< 3 navLabels; no-NCX flags), `toc_broken_links`, `guide_broken_links` | Carried. |
| Cover | `replaceable_cover` (+ `no_`), `calibre_svg_cover` (+ `no_`) | Carried; DRM-encrypted-cover and non-raster-extension rules verbatim. |
| Conversion | `conversion` (+ `not_converted`) | `calibre:timestamp` / `dc:contributor bkp` markers carried. |
| Style | `html_size` (> 260 KB), `drm`, `drm_meta` (adept.resource), `address`, `embedded_fonts`, `font_faces`, `xpgt_margins`, `inline_xpgt_links`, `css_justify`, `css_margins` (vs calibre page_setup defaults, 5pt fallback; titlepage skipped), `css_no_margins`, `inline_margins`, `javascript`, `smarten_punctuation` | Carried; the defaults comparison reads the plugin's own margins config (the calibre prefs read is the recorded substitution). |
| Declined | `check_epub_calibre_cover` | Deprecated upstream and unreachable from any menu key; dead code, not ported (recorded). |

### The saved-regex ePub content search

| Surface | Disposition | Notes |
|---|---|---|
| Regex search with scopes (html / plaintext / css / opf / ncx / zip), `ignore_case` default True, show-all-matches with 25-char context, first-match-stop | ported | A plugin verb; scope semantics carried (`check_epub.py:256-293`). |
| "Does not contain" (`exclude_matches`; flags books the expression matched NOTHING in; disables show-all) | ported | Carried (the 1.15.0 feature; negative lookahead does not work, this does). |
| History: gprefs `previous_finds`, deduped newest-first, `searchHistoryLength` default 10 | substituted | Plugin config storage (same cap, same dedupe order); gprefs is calibre's store. |

### Fix actions (11)

| Fix | Disposition | Notes |
|---|---|---|
| `fix_swap_author_names` (FN LN <-> LN, FN; polarity from first author) | ported | Selection-only upstream: requires an explicit target in the port (recorded). WriteGate. |
| `fix_author_initials` (four modes) | ported | Same targeting note; WriteGate. |
| `fix_author_ascii` (unidecode rename) | substituted | The NFKD approximation (same substitution as the check; recorded). |
| `fix_author_sort` / `fix_title_sort` (recompute + write) | ported | Through the host's sort seams. |
| `check_fix_book_size` (stored size vs filesystem; `format_metadata(update_db=True)`) | ported | Upstream requires calibre >= 5.9's API; the port's equivalent is the host's format-metadata rescan; floor note in the manifest when pinned. |
| `check_fix_book_paths` (comma-less folder repair via calibre's `construct_path_name`) | ported | The path-construction rule ports (author `|` -> `,` re-clause); the host's tree audit verifies the result. |
| `cleanup_opf_files` (save-to-disk orphan cleanup) | declined | On upstream's own warning: never run against the calibre library itself. Recorded. |
| `fix_mobi_asin` (ASIN priority: asin/mobi-asin -> amazon -> amazon_* -> uuid; EXTH 113/504/501 rebuild per format) | ported | The EXTH rebuild is a stdlib MOBI updater port (upstream extends calibre's `MetadataUpdater`); the recorded port work. |
| `fix_normalize_fields` (NFC over text fields except the composite/excluded set) | ported | The exclusion list carried verbatim. |
| `fix_normalize_notes` (NFC over category notes; calibre >= 7 notes API) | deferred | Needs a host notes surface; recorded as the named deferred shape until the host exposes notes access. |

### Config and exclusions

| Surface | Disposition | Notes |
|---|---|---|
| `maxTags`, `maxTagExclusions`, `authorInitialsMode`, `searchScope`, `hiddenMenus`, `suppressFixDialog`, `searchHistoryLength` (`config.py:174-177`) | ported / declined | The first four port as plugin config/flags; `hiddenMenus` and `suppressFixDialog` are GUI idioms, declined (recorded). |
| Exclusion lists per check (`exclusionsByCheck`, library-DB namespaced `QualityCheckPlugin/settings`, schema 1.9 migration, dead-id pruning) | substituted | Host persistent config keyed per library; the missing-data checks stay non-excludable (carried rule). |
| Action Chains hook (`action_chains.py`) | substituted | The plugin's verb surface IS the headless entry shape (fix key + target ids); no separate hook needed. |
