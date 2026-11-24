# Patchnotes

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
