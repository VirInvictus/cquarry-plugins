# Patchnotes

# Patchnotes

## v0.5.1

ERRATUM for v0.5.0, found by the dogfood drill the moment the package
loaded outside its repository root: the package's imports were ABSOLUTE
(`from quality_check import ...`), which only resolve when the repo root
happens to be on sys.path -- everywhere else the battery died with
ModuleNotFoundError before the first check ran. The imports are relative
(`from . import checks_db, checks_epub`) -- the layout the host
3.96.0 package loader's submodule_search_locations exists to support,
and exactly the multi-file shape the fixture plugin's test pins. No
other code moved. The dogfood drill after the fix: the verify/approve
gate passed, the missing-family battery flagged the scratch's blank
fields, the corrupt-placeholder file tripped corrupt_zip honestly, the
swap-fix dry plan named the swap, and search-epub's does-not-contain
ran clean.
# Patchnotes

## v0.5.0

The quality_check port lands (Phase 3): the battery as a multi-file
package riding host 3.96.0's package loader (api_version 3, floor
calibrequarry >= 3.96.1). Check families: metadata quality (sorts via
the engine's own helpers, ISBN checksums ported from calibre's
check_isbn, duplicate ISBN/series, series gaps and ordering, excess
tags, HTML-in-comments with upstream's comma bug as the recorded
correction, the author-format family with the NFKD-strip substitution,
title case via the ported titlecase), the 11 missing-data saved searches
carried verbatim, covers (size/dimensions/aspect via a stdlib
PNG-IHDR/JPEG-SOF parser -- the recorded PIL substitution), MOBI/AZW
(EBOK cdetype, ASIN, sharing, clipping via a minimal EXTH reader; Topaz
rejected like upstream), and the ePub structure/style battery (DRM,
containers, namespaces, manifest consistency both directions, unused
assets, broken links, cruft files, oversized HTML, TOC and guide checks,
covers, conversion markers, style patterns). The saved-regex content
search carries upstream's scopes (html/plaintext/css/opf/ncx/zip),
ignore-case, all-matches, and the does-not-contain flag. Fixes behind
the gates: author swap/reorder, initials format (the four modes),
ascii rename, author/title sort recomputation. Deferred with recorded
reasons: MOBI ASIN/cdetype repair (needs a MOBI writer), stored-size
repair (rides host 3.95.1's refresh seam, wired in v0.6.0's fix batch),
the save-to-disk orphan cleanup (declined on upstream's own warning),
and the css_margins prefs comparison (flag-only for now). The check
verb's error handling is honest: a raising check lands in a visible
check-errors section instead of vanishing (found live: the first
check_isbn port imported from plugin.py circularly and silently
vanished behind the battery's exception handler).
# Patchnotes

## v0.4.2

CARRIERS: v0.4.1 shipped with the root VERSION still reading 0.4.0 (the
bump script updated pyproject and patchnotes but missed the VERSION file
and pyproject), and the actions suite's version pin still asserted
0.4.0 -- the version-sync gate caught both, and the release went out
anyway, which is exactly the failure mode the gate exists to prevent.
This release moves the carriers and the pin; no other code moved.

# Patchnotes

## v0.4.1

ERRATUM for v0.4.0, whose CI ran red after the tag: the merge verb's
fill/union fields plan through seven WriteGate methods
(plan_set_authors, plan_add_tags, plan_set_languages, plan_set_rating,
plan_set_pubdate, plan_set_publisher, plan_set_comments) that were
written but left UNCOMMITTED in the host repo when v0.4.0 shipped, so
every merge test failed on the released host (`plan_set_authors`
missing). The host shipped them as calibrequarry 3.95.3; this release
changes exactly one thing: the manifest floor moves to
`calibrequarry >= 3.95.3`, so the version gates refuse v0.4.0's broken
dependency window the honest way. No other code moved.
# Patchnotes

## v0.4.0

The find_duplicates actions land (Phase 2's actions half, contract 3):
`merge --keeper ID --ids ID,ID [--fields ...]` carries calibre's merge
behind the gates -- formats copied into the keeper's directory and
registered (a format the keeper already carries stays), the chosen
fields fill/union into the keeper (a conflicting identifier is
reviewer-visible and never overwritten), and the absorbed rows are
removed in the same one-batch transaction; the plan prints in BOTH modes
(the plan is the record under --apply too, so a CONFLICT line is never
invisible), and the file copies happen outside the batch. The engine's
author re-lay renames the keeper's files after the authors change; the
tests resolve format paths through the engine for exactly that reason.
`remove-duplicate-formats --ids` keeps the earliest-mtime copy of each
byte-identical format; `delete --ids` is upstream's Delete key; the
`variations` report (authors/series/publishers/tags clusters per
matcher) supplies `rename --kind --from --to`. All actions are dry-run
by default, plan through the contract-3 plan seam, and execute through
the WriteGate's action seams (host >=3.95.2). Manifest: find_duplicates
0.4.0, api_version 3.
# Patchnotes

## v0.3.0

The find_duplicates port lands (Phase 2, the read half): the matcher
ladder carried verbatim (identical / similar with the automerge strip /
soundex with the adjustable per-field lengths / fuzzy with its aggressive
reductions, the author reversal hashes, the ignore-word lists; the
recorded tags-soundex length correction noted for the variations half),
the three search types (title/author with the reversed-author hash,
binary compare over the two-pass size-then-sha walk with an mtime-keyed
sha cache in the plugin config, identifier exact-equality), the grouping
pipeline with upstream's exemption partition (the don't-repartition
subtlety ported with its comment), per-library exemptions stored in the
plugin config under contract 2 (`exempt --books/--authors/--list/
--remove/--clear`; upstream's library-database prefs is the recorded
storage substitution, keyed by the absolute library path), the
cross-library mode (`search --against PATH`, report-only, no exemptions),
and the group report as text or `--format json` in upstream's export
shape (the recorded replacement for the GUI's marked-book highlighting).
Manifest: find_duplicates 0.3.0 on api_version 2, floor calibrequarry
>=3.95.0. The actions half (merge, binary-format removal, row deletion,
bulk rename, the variations reports) stays the recorded Phase 2 actions
box.
# Patchnotes

## v0.2.0

The extract_isbn port lands (Phase 1): the scanner (upstream's regex, strip
passes, -10/-13 prefix handling, same-digit rejection, and validation order;
the checksum formulas ported from calibre's check_isbn), the EPUB spine
windows (stdlib zip + container.xml + OPF parsing under the
EPUB_FILE_SCANS table), the PDF page windows (pdftotext + pdfinfo; the
100-byte near-empty extraction is the recorded encrypted/image-only
decline), and the scan verb with upstream's failure classes carried: the
dry run reports found / same / CONFLICT / none-found / no-format per book
(a stored different ISBN is reviewer-visible, never auto-overwritten; the
changed-ids line is pipe-ready) and the host's --apply writes through the
WriteGate. Manifests: extract_isbn 0.2.0 with the calibrequarry floor
raised to >=3.94.1 for the WriteGate label-pair fix. CI installs the host
pair from their mains; the suite runs the end-to-end verb over a scratch
library and the real poppler over crafted PDFs (skipped where poppler is
absent).
## v0.1.0

Initial skeleton: repository layout, GPL-3 license, the three plugin packages
with valid manifests (capabilities, api_version, cquarry and calibrequarry
version floors, upstream provenance), the manifest lint suite, the
version-sync pin, and house-hardened CI.
