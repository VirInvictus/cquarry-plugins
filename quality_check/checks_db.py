# Ported from kiwidude68/calibre_plugins quality_check (GPL-3), copyright
# kiwidude/Grant Drake, for the CalibreQuarry plugin host. The check
# battery's logic, thresholds, patterns, and the saved-regex search carry
# verbatim per the parity crosswalk (docs/crosswalk.md). Recorded
# substitutions: the unidecode checks approximate through an NFKD strip
# (the same recorded substitution as find_duplicates), the css_margins
# comparison reads no calibre page-setup prefs (the recorded substitution:
# flag margin blocks per the core patterns only), and the author-sort/
# title-sort computations ride the ENGINE's own helpers. Provenance:
# README.md and spec.md.

"""The check families that read the DATABASE (metadata quality, missing
data, covers, MOBI/AZW EXTH) plus the shared engines (titlecase, NFKD
approximation, image size). Each check returns True when the book is
FLAGGED (offending); None means "not applicable/skipped"."""

from __future__ import annotations

import re
import struct
from pathlib import Path

from quality_check.mobi_exth import NotMobiError, get_exth_field
from quality_check.titlecase import titlecase as _titlecase

DEFAULT_MAX_TAGS = 5
RE_HTML_CLOSING = re.compile(
    r"(</b>|</i>|</s>|</u>|</a>|</h\d>|</sub>|</sup>|</ol>|</ul>|</li>|</div>|</p>)",
    re.IGNORECASE,
)
IGNORE_AUTHOR_WORDS = frozenset(
    ["von", "van", "jr", "sr", "i", "ii", "iii", "second", "third", "md", "phd"]
)
IGNORE_INITIAL_TOKENS = frozenset(
    [
        "von",
        "van",
        "jr",
        "jr.",
        "sr",
        "sr.",
        "st",
        "st.",
        "ed",
        "ed.",
        "dr",
        "dr.",
        "phd",
        "ph.d",
        "ph.d.",
    ]
)


def _decode_ascii(text: str) -> str:
    """The NFKD-strip approximation (the recorded unidecode substitution)."""
    return (
        (unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii"))
        if (unicodedata := __import__("unicodedata"))
        else text
    )


def _initials_format(author: str, mode: str = "A.B.") -> str:
    """Upstream helpers.get_formatted_author_initials: the four target
    modes over the ignore-token rules (von/van/jr/... skipped unless
    ALL-CAPS; ii/iii always; numeric tokens skipped)."""
    tokens = re.split(r"\s+", author.strip())
    kept: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        if tok.isdigit():
            continue
        low = tok.lower().rstrip(".")
        if low in ("ii", "iii"):
            continue
        if low in IGNORE_INITIAL_TOKENS and not tok.isupper():
            continue
        kept.append(tok)
    initials: list[str] = []
    for tok in kept:
        if "." in tok or (tok.isupper() and len(tok) <= 2):
            initials.append(tok.rstrip(".")[0].upper())
        elif len(tok) > 1:
            initials.append(tok[0].upper())
    joined = "".join(initials)
    if mode == "A.B.":
        return ".".join(joined) + "."
    if mode == "A. B.":
        return " ".join(c + "." for c in joined)
    if mode == "A B":
        return " ".join(joined)
    return joined


def formatted_author_initials(author: str, mode: str = "A.B.") -> str:
    return _initials_format(author, mode)


# ------------------------------------------------------------- image size


def image_dimensions(path: Path) -> tuple[int, int] | None:
    """PNG IHDR / JPEG SOF dimensions in stdlib (the recorded PIL
    substitution)."""
    data = path.read_bytes()[: 64 * 1024]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if data[12:16] == b"IHDR":
            w, h = struct.unpack(">II", data[16:24])
            return w, h
        return None
    if data[:2] == b"\xff\xd8":
        pos = 2
        while pos < len(data) - 9:
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in (
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            ):
                h, w = struct.unpack(">HH", data[pos + 5 : pos + 9])
                return w, h
            seg_len = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
            pos += 2 + seg_len
    return None


# --------------------------------------------------------- metadata checks


def check_title_sort(db, book_id) -> bool:
    from cquarry.helpers import title_sort

    book = db.get_book(book_id, include_comments=False)
    if not book:
        return False
    row = db.conn.execute("SELECT sort FROM books WHERE id = ?", (book_id,)).fetchone()
    stored = row[0] if row else ""
    return stored != title_sort(book["title"])


def check_isbn_checksum(db, book_id) -> bool:
    isbn = db.get_identifiers(book_id).get("isbn", "")
    if not isbn:
        return False
    return not _check_isbn_text(isbn)


def _check_isbn_text(text: str) -> bool:
    """ISBN-10 (mod 11, X check) / ISBN-13 (mod 10, 1-3 weights)."""
    digits = re.sub("[^0-9X]", "", text.upper())
    if len(digits) == 10:
        if not digits[:9].isdigit():
            return False
        total = 0
        for i in range(10):
            value = (
                10
                if (i == 9 and digits[i] == "X")
                else (int(digits[i]) if digits[i].isdigit() else -1)
            )
            if value < 0:
                return False
            total += (10 - i) * value
        return total % 11 == 0
    if len(digits) == 13:
        if not digits.isdigit():
            return False
        total = sum((1 if i % 2 == 0 else 3) * int(digits[i]) for i in range(13))
        return total % 10 == 0
    return False


def check_author_sort(db, book_id) -> bool:
    book = db.get_book(book_id, include_comments=False)
    if not book:
        return False
    computed = (
        " & ".join(
            (a.get("sort") or a.get("name", ""))
            for a in (book.get("author_sort_map") or [])
        )
        if isinstance(book.get("author_sort_map"), list)
        else None
    )
    # the engine's stored author_sort vs the authors' sort fields
    stored = book.get("author_sort") or ""
    sort_fields = [
        r[0]
        for r in db.conn.execute(
            "SELECT a.sort FROM books_authors_link bl JOIN authors a"
            " ON a.id = bl.author WHERE bl.book = ? ORDER BY a.sort",
            (book_id,),
        ).fetchall()
    ]
    computed = " & ".join(s for s in sort_fields if s)
    return (stored != computed) if computed else False


def check_pubdate_unchanged(db, book_id) -> bool:
    book = db.get_book(book_id, include_comments=False)
    if not book:
        return False
    return bool(book.get("pubdate")) and book.get("timestamp") == book.get("pubdate")


def check_duplicate_isbn(db, book_id, groups) -> bool:
    isbn = db.get_identifiers(book_id).get("isbn", "")
    return bool(isbn) and len(groups.get(isbn, ())) > 1


def check_duplicate_series(db, book_id, groups) -> bool:
    book = db.get_book(book_id, include_comments=False)
    series = book.get("series") if book else None
    if not series:
        return False
    key = (series, round(float(book.get("series_index") or 0), 4))
    return len(groups.get(key, ())) > 1


def check_series_gaps(db, book_id, indexes_by_series) -> bool:
    book = db.get_book(book_id, include_comments=False)
    series = book.get("series") if book else None
    if not series:
        return False
    idx = book.get("series_index")
    if idx is None or idx < 1 or idx != int(idx):
        return False
    max_index = indexes_by_series.get(series, 0)
    if max_index >= 1000:
        return False
    all_ints = indexes_by_series.get(f"{series}:ints", set())
    return any(m not in all_ints for m in range(1, int(idx)))


def check_series_pubdate_order(db, book_id, ordered) -> bool:
    return (book_id, False) in ordered


def check_excess_tags(db, book_id, max_tags, exclusions=()) -> bool:
    book = db.get_book(book_id, include_comments=False)
    tags = book.get("tags") or [] if book else []
    counted = [t for t in tags if t not in exclusions]
    return len(counted) > max_tags


def check_html_in_comments(db, book_id) -> bool:
    book = db.get_book(book_id, include_comments=True)
    comments = book.get("comments") if book else None
    return bool(comments and RE_HTML_CLOSING.search(comments))


def check_no_html_in_comments(db, book_id) -> bool:
    book = db.get_book(book_id, include_comments=True)
    comments = book.get("comments") if book else None
    # upstream's intended pattern list (its comma bug is the recorded
    # correction); a book with plain-text comments flags here
    return bool(comments and not RE_HTML_CLOSING.search(comments))


def check_authors_commas(db, book_id) -> bool:
    return any("," in a or "|" in a for a in _book_authors(db, book_id))


def check_authors_no_commas(db, book_id) -> bool:
    return any("," not in a and "|" not in a for a in _book_authors(db, book_id))


def check_authors_case(db, book_id) -> bool:
    return any(
        a.isupper() or a.islower() for a in _book_authors(db, book_id) if len(a) > 1
    )


def check_authors_non_alpha(db, book_id) -> bool:
    for author in _book_authors(db, book_id):
        decoded = _decode_ascii(author)
        if re.search(r"[^A-Za-z'\.,\- ]", decoded):
            return True
    return False


def check_authors_non_ascii(db, book_id) -> bool:
    return any(_decode_ascii(a) != a for a in _book_authors(db, book_id))


def check_authors_initials(db, book_id, mode="A.B.") -> bool:
    return any(_initials_format(a, mode) != a for a in _book_authors(db, book_id))


def check_titles_with_series_info(db, book_id) -> bool:
    book = db.get_book(book_id, include_comments=False)
    title = book.get("title", "") if book else ""
    return bool(title) and ("-" in title or re.match(r"[0-9]", title))


def check_title_case(db, book_id) -> bool:
    book = db.get_book(book_id, include_comments=False)
    title = book.get("title", "") if book else ""
    return bool(title) and title != _titlecase(title)


def _book_authors(db, book_id) -> list[str]:
    book = db.get_book(book_id, include_comments=False)
    return list(book.get("authors") or []) if book else []


# ----------------------------------------------------------- missing family
# Upstream's 11 missing-data checks are literally saved-search expressions
# (check_missing.py:19-41); each carries verbatim, run through the host's
# search API.

MISSING_SEARCHES = (
    ("check_missing_title", 'title:"=Unknown"'),
    ("check_missing_author", 'authors:"=Unknown"'),
    ("check_missing_isbn", "isbn:False"),
    ("check_missing_pubdate", "pubdate:False"),
    ("check_missing_publisher", "publisher:False"),
    ("check_missing_tags", "tags:False"),
    ("check_missing_rating", "rating:False"),
    ("check_missing_comments", "comments:False"),
    ("check_missing_languages", "languages:False"),
    ("check_missing_cover", "cover:False"),
    ("check_missing_formats", "formats:False"),
)


# ------------------------------------------------------------- cover family


def check_cover_size(db, book_id, less, kb) -> bool:
    """Size mode: flag when size < kb (less) or size > kb."""
    path = _cover_path(db, book_id)
    if not path or not path.exists():
        return less is None  # the no-cover option is a separate saved search
    size_kb = path.stat().st_size / 1024
    return size_kb < kb if less else size_kb > kb


def check_cover_dimensions(db, book_id, op, w, h) -> bool:
    path = _cover_path(db, book_id)
    if not path or not path.exists():
        return False
    dims = image_dimensions(path)
    if dims is None:
        return False
    cw, ch = dims
    if op == "lt":
        return (w and cw < w) or (h and ch < h)
    if op == "gt":
        return (w and cw > w) or (h and ch > h)
    if op == "eq":
        return (cw == w if w else True) and (ch == h if h else True)
    if op == "neq":
        return (cw != w if w else False) or (ch != h if h else False)
    return False


def check_cover_aspect(db, book_id, op, ratio, tolerance_pct) -> bool:
    path = _cover_path(db, book_id)
    if not path or not path.exists():
        return False
    dims = image_dimensions(path)
    if not dims or not dims[1]:
        return False
    actual = dims[0] / dims[1]
    tolerance = tolerance_pct * ratio / 100
    low, high = ratio - tolerance, ratio + tolerance
    if op == "lt":
        return actual < low
    if op == "gt":
        return actual > high
    if op == "eq":
        return low <= actual <= high
    if op == "neq":
        return actual < low or actual > high
    return False


def _cover_path(db, book_id) -> Path | None:
    book = db.get_book(book_id, include_comments=False)
    if not book or not book.get("has_cover"):
        return None
    root = Path(db.db_path).parent
    return root / book["path"] / "cover.jpg"


# ------------------------------------------------------------- MOBI family

MOBI_FORMATS = ("MOBI", "AZW", "AZW3")


def check_mobi_missing_ebok(db, book_id) -> bool:
    return _mobi_check(
        db, book_id, lambda exth: exth.get(501, b"EBOK") != b"EBOK" or True
    )


def _mobi_check(db, book_id, predicate) -> bool:
    """True when ANY MOBI-family format of the book trips the predicate.
    No EXTH at all flags missing_ebok/asin like upstream."""
    for fmt, path in _mobi_paths(db, book_id):
        try:
            exth = get_exth_field and _read_exth_map(path)
        except NotMobiError, ValueError, OSError:
            continue
        if predicate(exth):
            return True
    return False


def _read_exth_map(path):
    from quality_check.mobi_exth import read_exth

    return read_exth(path)


def _mobi_paths(db, book_id):
    from pathlib import Path as _P

    root = _P(db.db_path).parent
    book = db.get_book(book_id, include_comments=False)
    if not book:
        return []
    out = []
    for fmt, detail in db.get_formats(book_id).items():
        if fmt.upper() not in MOBI_FORMATS:
            continue
        p = root / book["path"] / f"{detail['name']}.{fmt.lower()}"
        if p.exists():
            out.append((fmt, p))
    return out
