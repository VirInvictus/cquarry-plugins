# Patchnotes

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
