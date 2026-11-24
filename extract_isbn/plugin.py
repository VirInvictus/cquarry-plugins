# Ported from kiwidude68/calibre_plugins extract_isbn (GPL-3), copyright
# 2011 Grant Drake, for the CalibreQuarry plugin host. The scan regex, the
# strip passes, the -10/-13 prefix handling, the same-digit rejection, the
# validation order, the EPUB_FILE_SCANS window table, and the front /
# rear-reversed / middle walk order are upstream's, carried verbatim per
# the parity crosswalk (docs/crosswalk.md). The checksum formulas are
# ported from calibre's ebooks.metadata.check_isbn (GPL-3). Recorded
# substitutions (crosswalk rows): calibre's EbookIterator becomes stdlib
# zip + container.xml + OPF spine parsing; the HTMLPreProcessor pass is
# not ported (it services calibre's converter; raw utf-8 replace decoding
# suffices for scanning); pdftohtml becomes pdftotext with pdfinfo for
# the page count. Provenance: this package's README.md and spec.md.

"""The extract_isbn plugin: printed ISBNs from book files, adopted into
the library's isbn identifiers.

Scan contract (1:1 with upstream): the book's formats are tried in the
preference order (EPUB first, PDF near-last, TXT last), the first format
yielding an ISBN stops, PDFs read the first 10 pages then the last 5 (one
whole-document pass at 15 pages or fewer, page count via pdfinfo), EPUBs
walk the spine (front forward, rear reversed, middle forward per
EPUB_FILE_SCANS), TXT reads whole, and the ISBN rules are upstream's: the
9-22 char window ending in a digit or x/X, style blocks stripped, tags
replaced with ``!``, the ``-10 ``/``-13 `` prefix strip, the
all-identical-digit rejection, ISBN-13s gated on the prefix set (default
977/978/979, ``--prefixes`` extends it) then checksummed, ISBN-10s
checksummed with no prefix gate, first ISBN-13 else first ISBN-10.

Write policy (the host's recorded rule, stricter than upstream's
overwrite): a stored identical isbn skips; a stored DIFFERENT isbn skips
and reports (a conflict is reviewer-visible, never auto-overwritten); an
absent isbn writes through the host's WriteGate. The dry run IS the
prompt; the report's changed-ids line is pipe-ready.
"""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote

# The engine's own format preference order (EPUB first, PDF near-last,
# TXT last; unknown formats keep library order after the known ones).
FORMAT_PREFERENCE = (
    "EPUB",
    "AZW3",
    "MOBI",
    "LIT",
    "PRC",
    "FB2",
    "HTML",
    "HTM",
    "XHTM",
    "SHTML",
    "XHTML",
    "ZIP",
    "DOCX",
    "ODT",
    "RTF",
    "PDF",
    "TXT",
)
PDF_FRONT_PAGES = 10
PDF_BACK_PAGES = 5
PDF_WHOLE_PASS_MAX = PDF_FRONT_PAGES + PDF_BACK_PAGES
# Upstream's DRM heuristic: an extraction this small is not a real
# copyright page, it is an encrypted or image-only file.
MIN_TEXT_BYTES = 100

# (Min #files, #files at start, #files at end to scan in reverse)
EPUB_FILE_SCANS = [
    (15, 10, -5),
    (10, 6, -4),
    (6, 4, -2),
    (3, 2, -1),
    (2, 1, -1),
    (1, 1, 0),
]


def _spawn(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    """The read-only poppler spawn: text mode decodes with errors=replace."""
    proc = subprocess.run(
        cmd, capture_output=True, text=True, errors="replace", timeout=timeout
    )
    return proc.returncode, proc.stdout, proc.stderr


# ---------------------------------------------------------------- scanner

RE_ISBN = re.compile(
    "\\s*([0-9\\-\.\u2013\u00ad\u2015\u2014\\^ ]{9,22}[0-9xX])", re.UNICODE
)
RE_STRIP_STYLE = re.compile("<style[^<]+</style>", re.MULTILINE | re.UNICODE)
RE_STRIP_MARKUP = re.compile("<[^>]+>", re.UNICODE)
RE_SAME_DIGIT = re.compile(r"(\d)\1{9,12}$")

DEFAULT_ISBN13_PREFIXES = ("977", "978", "979")


def _check_isbn10(text: str) -> bool:
    if len(text) != 10 or not text[:9].isdigit():
        return False
    total = 0
    for i in range(10):
        char = text[i]
        if i == 9 and char in "Xx":
            value = 10
        elif char.isdigit():
            value = int(char)
        else:
            return False
        total += (10 - i) * value
    return total % 11 == 0


def _check_isbn13(text: str) -> bool:
    if len(text) != 13 or not text.isdigit():
        return False
    total = 0
    for i in range(13):
        total += (1 if i % 2 == 0 else 3) * int(text[i])
    return total % 10 == 0


def check_isbn(text: str) -> bool:
    """Checksum validation for both notations (the calibre check_isbn port)."""
    if len(text) == 10:
        return _check_isbn10(text)
    if len(text) == 13:
        return _check_isbn13(text)
    return False


class BookScanner:
    """Upstream's scanner: collect candidates, validate, prefer 13 over 10."""

    def __init__(
        self, valid_isbn13s: tuple[str, ...] = DEFAULT_ISBN13_PREFIXES
    ) -> None:
        self.isbns10: list[str] = []
        self.isbns13: list[str] = []
        self.valid_isbn13s = tuple(valid_isbn13s)

    def get_isbn_result(self) -> str | None:
        if self.isbns13:
            return self.isbns13[0]
        if self.isbns10:
            return self.isbns10[0]
        return None

    def has_identifier(self) -> bool:
        return len(self.isbns13) + len(self.isbns10) > 0

    def look_for_identifiers_in_text(
        self, book_files: list[str], forward: bool = True
    ) -> None:
        """Scan text chunks for identifiers; stops once one valid ISBN exists."""
        if not forward:
            book_files = list(reversed(book_files))
        for book_file in book_files:
            # Strip all the html markup tags out in case we get clashes with
            # svg covers (upstream's own comment; the behavior is the point).
            book_file = RE_STRIP_STYLE.sub("", book_file)
            book_file = RE_STRIP_MARKUP.sub("!", book_file)
            if forward:
                for match in RE_ISBN.finditer(book_file):
                    txt = match.group(1)
                    # PDF formatting can spread an ISBN over multiple lines.
                    txt = txt.replace("\n", "")
                    self._evaluate_isbn_match(txt)
            else:
                matches = RE_ISBN.findall(book_file)
                for match in reversed(matches):
                    self._evaluate_isbn_match(match)
            if self.has_identifier():
                break

    def _evaluate_isbn_match(self, original_text: str) -> None:
        # The regex can get "fooled" by "ISBN-10 1-4020-4136-5": it returns
        # "-10 1-4020-4136-5", so strip the 4-char prefix (upstream's rule).
        if original_text.startswith("-10 ") or original_text.startswith("-13 "):
            original_text = original_text[4:]
        txt = re.sub("[^0-9X]", "", original_text)
        txt_len = len(txt)
        # Repeating digits like 1111111111 are never ISBNs (upstream kept
        # this even after calibre grew its own check).
        all_same = RE_SAME_DIGIT.match(txt)
        if all_same is None:
            if txt_len == 10:
                if check_isbn(txt):
                    self.isbns10.append(txt)
                    return
            elif txt_len == 13:
                if txt[:3] in self.valid_isbn13s:
                    if check_isbn(txt):
                        self.isbns13.append(txt)
                        return


def scan_texts(
    texts: list[str],
    forward: bool = True,
    prefixes: tuple[str, ...] = DEFAULT_ISBN13_PREFIXES,
) -> str | None:
    """One-shot scan over prepared text chunks (the scanner's thin driver)."""
    scanner = BookScanner(prefixes)
    scanner.look_for_identifiers_in_text(texts, forward=forward)
    return scanner.get_isbn_result()


# ------------------------------------------------------------------- EPUB


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _spine_paths(epub_path: Path) -> list[str]:
    """The spine's member names, in order, via container.xml + OPF."""
    with zipfile.ZipFile(epub_path) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        opf_path = None
        for el in container.iter():
            if _local(el.tag) == "rootfile" and el.get("full-path"):
                opf_path = el.get("full-path")
                break
        if opf_path is None:
            raise ValueError("no rootfile in the container.xml")
        opf = ET.fromstring(archive.read(opf_path))
        hrefs: dict[str, str] = {}
        spine_ids: list[str] = []
        for el in opf.iter():
            if _local(el.tag) == "item" and el.get("id") and el.get("href"):
                hrefs[el.get("id")] = el.get("href")
            elif _local(el.tag) == "itemref" and el.get("idref"):
                spine_ids.append(el.get("idref"))
        opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
        names: list[str] = []
        for idref in spine_ids:
            href = hrefs.get(idref)
            if href is None:
                continue
            href = unquote(href.split("#", 1)[0])
            names.append(f"{opf_dir}/{href}" if opf_dir else href)
        return names


def scan_epub(epub_path: Path, prefixes: tuple[str, ...]) -> tuple[str | None, str]:
    """Scan one EPUB under the upstream windows; (isbn|None, detail)."""
    try:
        names = _spine_paths(epub_path)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as e:
        return None, f"unreadable EPUB: {e}"
    if not names:
        return None, "empty spine"
    count = len(names)
    first_files: list[str] = []
    last_files: list[str] = []
    middle_files: list[str] = []
    for min_files, front_count, rear_count in EPUB_FILE_SCANS:
        if count >= min_files:
            first_files = names[:front_count]
            if rear_count != 0:
                last_files = names[rear_count:]
            if count - min_files > 0:
                middle_files = names[front_count:rear_count]
            break
    missing = 0
    hit: tuple[str, str] | None = None
    try:
        with zipfile.ZipFile(epub_path) as archive:
            available = set(archive.namelist())

            def read(name: str) -> str | None:
                nonlocal missing
                if name not in available:
                    missing += 1
                    return None
                return archive.read(name).decode("utf-8", "replace")

            for name in first_files:
                text = read(name)
                if text is None:
                    continue
                isbn = scan_texts([text], forward=True, prefixes=prefixes)
                if isbn:
                    hit = (isbn, f"front file {name}")
                    break
            if hit is None:
                for name in reversed(last_files):
                    text = read(name)
                    if text is None:
                        continue
                    isbn = scan_texts([text], forward=False, prefixes=prefixes)
                    if isbn:
                        hit = (isbn, f"rear file {name} (reversed)")
                        break
            if hit is None:
                for name in middle_files:
                    text = read(name)
                    if text is None:
                        continue
                    isbn = scan_texts([text], forward=True, prefixes=prefixes)
                    if isbn:
                        hit = (isbn, f"middle file {name}")
                        break
    except zipfile.BadZipFile as e:
        return None, f"unreadable EPUB: {e}"
    if hit is not None:
        return hit
    detail = (
        f"no isbn in the first {len(first_files)}, last {len(last_files)}, and "
        f"remaining {len(middle_files)} of {count} spine file(s)"
    )
    if missing:
        detail += f"; {missing} spine file(s) missing from the archive"
    return None, detail


# -------------------------------------------------------------------- PDF


def _pdf_page_count(path: Path) -> int | None:
    try:
        _rc, out, _err = _spawn(["pdfinfo", str(path)], timeout=60)
    except OSError, subprocess.TimeoutExpired:
        return None
    match = re.search(r"^Pages:\s+(\d+)$", out, re.MULTILINE)
    return int(match.group(1)) if match else None


def _pdftotext(path: Path, first: int | None, last: int | None) -> str:
    cmd = ["pdftotext", "-enc", "UTF-8"]
    if first is not None:
        cmd += ["-f", str(first), "-l", str(last)]
    cmd += [str(path), "-"]
    _rc, out, _err = _spawn(cmd)
    return out


def scan_pdf(path: Path, prefixes: tuple[str, ...]) -> tuple[str | None, str]:
    """Scan one PDF under the upstream windows; (isbn|None, detail)."""
    pages = _pdf_page_count(path)
    if pages is None:
        return None, "page count unavailable (pdfinfo)"
    windows: list[tuple[int | None, int | None]] = []
    if pages <= PDF_WHOLE_PASS_MAX:
        windows.append((None, None))
    else:
        windows.append((1, PDF_FRONT_PAGES))
        windows.append((pages - PDF_BACK_PAGES + 1, pages))
    for first, last in windows:
        span = f"pages {first}-{last}" if first is not None else f"all {pages} pages"
        text = _pdftotext(path, first, last)
        if len(text.encode("utf-8", "replace")) < MIN_TEXT_BYTES:
            return (
                None,
                f"{span}: empty or near-empty extraction (the encrypted or "
                "image-only class)",
            )
        isbn = scan_texts([text], forward=True, prefixes=prefixes)
        if isbn:
            return isbn, span
    spans = (
        "all pages"
        if windows[0] == (None, None)
        else (f"pages 1-{PDF_FRONT_PAGES} then the last {PDF_BACK_PAGES}")
    )
    return None, f"no isbn in {spans} of {pages}"


# ------------------------------------------------------------------- text


def scan_text_file(path: Path, prefixes: tuple[str, ...]) -> tuple[str | None, str]:
    text = path.read_bytes().decode("utf-8", "replace")
    isbn = scan_texts([text], forward=True, prefixes=prefixes)
    return (isbn, "whole file") if isbn else (None, "no isbn in the whole file")


# ------------------------------------------------------------------- verb


def _parse_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return ids


def _ordered_formats(paths: dict) -> list[tuple[str, Path]]:
    known = [f for f in FORMAT_PREFERENCE if f in paths]
    unknown = sorted(f for f in paths if f not in FORMAT_PREFERENCE)
    return [(fmt, paths[fmt]) for fmt in known + unknown]


def scan(context, argv: list[str]) -> int:
    """The scan verb: report found ISBNs; --apply (host flag) writes them."""
    prefixes = tuple(DEFAULT_ISBN13_PREFIXES)
    ids: set[int] | None = None
    search: str | None = None
    it = iter(argv)
    for arg in it:
        if arg == "--prefixes":
            prefixes = tuple(p.strip() for p in next(it).split(",") if p.strip())
        elif arg == "--ids":
            ids = set(_parse_ids(next(it)))
        elif arg == "--search":
            search = next(it)
        else:
            context.log(f"scan: unknown argument {arg!r} ignored")
    db = context.db
    if search is not None:
        targets = set(db.search(search))
    elif ids is not None:
        targets = ids
    else:
        targets = set(db.all_ids())

    counts = {"write": 0, "same": 0, "conflict": 0, "none": 0, "noformat": 0}
    write_rows: list[tuple[int, str]] = []
    lines: list[str] = [f"scan: {len(targets)} book(s) in scope"]
    for book_id in sorted(targets):
        book = db.get_book(book_id, include_comments=False)
        title = book["title"] if book else f"book {book_id}"
        stored = db.get_identifiers(book_id).get("isbn")
        paths = context.format_paths(book_id)
        if not paths:
            counts["noformat"] += 1
            lines.append(f"  #{book_id} {title}: no formats on the book")
            continue
        found: str | None = None
        detail = ""
        for fmt, path in _ordered_formats(paths):
            if fmt == "EPUB":
                found, detail = scan_epub(path, prefixes)
            elif fmt == "PDF":
                found, detail = scan_pdf(path, prefixes)
            elif fmt == "TXT":
                found, detail = scan_text_file(path, prefixes)
            else:
                detail = f"{fmt}: not supported by the stdlib scanner (deferred)"
                continue
            if found:
                break
        if found is None:
            counts["none"] += 1
            lines.append(f"  #{book_id} {title}: no isbn found ({detail})")
        elif stored == found:
            counts["same"] += 1
            lines.append(f"  #{book_id} {title}: same isbn stored ({found}), skipped")
        elif stored is not None:
            counts["conflict"] += 1
            lines.append(
                f"  #{book_id} {title}: CONFLICT, stored {stored} vs found {found} "
                f"({detail}); review, never auto-overwritten"
            )
        else:
            counts["write"] += 1
            write_rows.append((book_id, found))
            lines.append(f"  #{book_id} {title}: found {found} ({detail})")
    summary = (
        f"summary: {counts['write']} write, {counts['same']} same, "
        f"{counts['conflict']} conflict, {counts['none']} none-found, "
        f"{counts['noformat']} no-format"
    )
    lines.append(summary)
    if write_rows:
        lines.append("changed ids: " + ",".join(str(bid) for bid, _ in write_rows))
    for line in lines:
        print(line)
    if not context.can_write:
        return 0
    if not write_rows:
        return 0
    actions = [
        context.write.plan_identifier(bid, "isbn", isbn) for bid, isbn in write_rows
    ]
    code = context.write.apply(context.db_path, actions)
    print(f"applied {len(write_rows)} identifier write(s)")
    return code


def register(context):
    return {"scan": scan}
