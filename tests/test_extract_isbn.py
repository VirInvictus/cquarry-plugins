"""The extract_isbn port's suite: scanner units, window walks, and the
end-to-end verb through the host's WriteGate.

The PDF window logic is unit-tested against a mocked spawn; one live class
runs the real poppler over a crafted 20-page PDF (skipped on CI, which has
no poppler: the house skipUnless convention). The end-to-end tests run the
loaded plugin through the host's harness against a scratch library (the
host is a declared test dependency; ci.yml installs it).
"""

import contextlib
import importlib.util
import io
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO / "extract_isbn"

try:
    from cquarry_cli.plugins.gates import PluginContext
    from cquarry_cli.plugins.harness import verify
    from cquarry_cli.plugins.manifest import load_manifest as _load_manifest
    from cquarry_cli.plugins.scratch import build_scratch
    from cquarry_cli.plugins.verbs import run_plugin_verb

    HOST_AVAILABLE = True
except ImportError:  # pragma: no cover - CI installs the host before the suite
    HOST_AVAILABLE = False

PDF_TOOLS = bool(shutil.which("pdftotext") and shutil.which("pdfinfo"))


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "cquarry_plugin_extract_isbn_test", PLUGIN_DIR / "plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plugin = _load_plugin()

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""


def _opf(doc_count: int) -> str:
    items = "\n".join(
        f'<item id="d{i}" href="doc{i}.xhtml" media-type="application/xhtml+xml"/>'
        for i in range(1, doc_count + 1)
    )
    spine = "\n".join(f'<itemref idref="d{i}"/>' for i in range(1, doc_count + 1))
    return (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
        f"<metadata/><manifest>{items}</manifest><spine>{spine}</spine></package>"
    )


def _make_epub(path: Path, docs: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("content.opf", _opf(len(docs)))
        for i, doc in enumerate(docs, 1):
            z.writestr(f"doc{i}.xhtml", doc)


def _make_pdf(path: Path, page_count: int, text_by_page: dict[int, str]) -> None:
    """A minimal single-font PDF; enough for poppler to extract Tj text."""
    objects: list[bytes] = []
    kids = " ".join(f"{3 + i} 0 R" for i in range(page_count))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())
    for i in range(page_count):
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /Contents {3 + page_count + i} 0 R "
            "/Resources << /Font << /F1 "
            f"{3 + page_count * 2} 0 R >> >> >>".encode()
        )
    for i in range(page_count):
        text = text_by_page.get(i + 1, "")
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for idx, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(out))


GOOD_13 = "9780140445688"
OTHER_13 = "9780195019193"


class TestScanner(unittest.TestCase):
    def test_labelled_dashed_13_found(self) -> None:
        isbn = plugin.scan_texts(
            ["Copyright page: ISBN 978-0-14-044568-8 printed here."]
        )
        self.assertEqual(isbn, GOOD_13)

    def test_isbn13_prefix_label_stripped(self) -> None:
        isbn = plugin.scan_texts(["ISBN-13 978-0-14-044568-8"])
        self.assertEqual(isbn, GOOD_13)

    def test_valid_10_with_x_check_found(self) -> None:
        isbn = plugin.scan_texts(["ISBN 0-8044-2957-X"])
        self.assertEqual(isbn, "080442957X")

    def test_10_form_of_the_13_found(self) -> None:
        isbn = plugin.scan_texts(["ISBN 0-14-044568-4"])
        self.assertEqual(isbn, "0140445684")

    def test_invalid_checksum_rejected(self) -> None:
        self.assertIsNone(plugin.scan_texts(["ISBN 978-0-14-044568-7"]))

    def test_prefix_gate_rejects_unknown_13(self) -> None:
        # 9800000000007 carries a valid checksum but the 980 prefix is not
        # in the default set.
        self.assertIsNone(
            plugin.scan_texts(["ISBN 980-0-000-000-000-7".replace("-", "")])
        )

    def test_prefix_extension_accepts(self) -> None:
        isbn = plugin.scan_texts(
            ["ISBN 9800000000007"], prefixes=("977", "978", "979", "980")
        )
        self.assertEqual(isbn, "9800000000007")

    def test_10_has_no_prefix_gate(self) -> None:
        # A checksum-valid 10-form whose 978-cross is fine but whose own
        # leading digits are nothing special.
        isbn = plugin.scan_texts(["ISBN 0-14-044568-4"])
        self.assertEqual(isbn, "0140445684")

    def test_first_13_preferred_over_10(self) -> None:
        text = "ISBN 0-14-044568-4 and ISBN 978-0-14-044568-8"
        self.assertEqual(plugin.scan_texts([text]), GOOD_13)

    def test_rear_direction_scans_backwards(self) -> None:
        text = "tail 978-0-19-501919-3 head " + GOOD_13
        # forward: the first valid match in text order wins; backward: the
        # last one (the reversed evaluation order fills the list first).
        self.assertEqual(plugin.scan_texts([text], forward=True), OTHER_13)
        self.assertEqual(plugin.scan_texts([text], forward=False), GOOD_13)

    def test_style_blocks_stripped(self) -> None:
        text = "<style>.x { content: 'ISBN 978-0-14-044568-8'; }</style><p>nothing</p>"
        self.assertIsNone(plugin.scan_texts([text]))


class TestEpubSpine(unittest.TestCase):
    def test_three_doc_spine_finds_rear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            docs = [f"<html><p>chapter {i}</p></html>" for i in range(1, 4)]
            docs[2] = "<html><p>ISBN 978-0-14-044568-8</p></html>"
            _make_epub(path, docs)
            isbn, detail = plugin.scan_epub(path, plugin.DEFAULT_ISBN13_PREFIXES)
            self.assertEqual(isbn, GOOD_13)
            self.assertIn("rear file", detail)

    def test_middle_window_scanned_last(self) -> None:
        # The middle IS scanned, after front and rear fail (upstream's walk
        # order); a hit there reports the middle file.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            docs = [f"<html><p>chapter {i}</p></html>" for i in range(1, 21)]
            docs[11] = "<html><p>ISBN 978-0-14-044568-8</p></html>"  # doc 12
            _make_epub(path, docs)
            isbn, detail = plugin.scan_epub(path, plugin.DEFAULT_ISBN13_PREFIXES)
            self.assertEqual(isbn, GOOD_13)
            self.assertIn("middle file", detail)

    def test_rear_window_of_a_20_doc_spine_scanned_reversed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            docs = [f"<html><p>chapter {i}</p></html>" for i in range(1, 21)]
            docs[17] = "<html><p>ISBN 978-0-14-044568-8</p></html>"  # doc 18
            _make_epub(path, docs)
            isbn, detail = plugin.scan_epub(path, plugin.DEFAULT_ISBN13_PREFIXES)
            self.assertEqual(isbn, GOOD_13)
            self.assertIn("rear file", detail)

    def test_front_window_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            docs = [f"<html><p>chapter {i}</p></html>" for i in range(1, 21)]
            docs[1] = "<html><p>ISBN 978-0-14-044568-8</p></html>"  # doc 2
            _make_epub(path, docs)
            isbn, detail = plugin.scan_epub(path, plugin.DEFAULT_ISBN13_PREFIXES)
            self.assertEqual(isbn, GOOD_13)
            self.assertIn("front file", detail)

    def test_unreadable_zip_declines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.epub"
            path.write_bytes(b"not a zip")
            isbn, detail = plugin.scan_epub(path, plugin.DEFAULT_ISBN13_PREFIXES)
            self.assertIsNone(isbn)
            self.assertIn("unreadable EPUB", detail)


class TestPdfWindows(unittest.TestCase):
    def test_whole_pass_at_15_pages(self) -> None:
        calls = []

        def fake_spawn(cmd, timeout=300):
            calls.append(cmd)
            if cmd[0] == "pdfinfo":
                return 0, "Pages:          15\n", ""
            return 0, "x" * 200 + f" {GOOD_13}", ""

        with mock.patch.object(plugin, "_spawn", side_effect=fake_spawn):
            isbn, detail = plugin.scan_pdf(
                Path("book.pdf"), plugin.DEFAULT_ISBN13_PREFIXES
            )
        self.assertEqual(isbn, GOOD_13)
        self.assertIn("all 15 pages", detail)
        text_call = [c for c in calls if c[0] == "pdftotext"][0]
        self.assertNotIn("-f", text_call)

    def test_two_windows_over_20_pages(self) -> None:
        calls = []

        def fake_spawn(cmd, timeout=300):
            calls.append(cmd)
            if cmd[0] == "pdfinfo":
                return 0, "Pages:          20\n", ""
            first = int(cmd[cmd.index("-f") + 1])
            if first == 16:
                return 0, "y" * 200 + f" {GOOD_13}", ""
            return 0, "x" * 200, ""

        with mock.patch.object(plugin, "_spawn", side_effect=fake_spawn):
            isbn, detail = plugin.scan_pdf(
                Path("book.pdf"), plugin.DEFAULT_ISBN13_PREFIXES
            )
        self.assertEqual(isbn, GOOD_13)
        self.assertIn("pages 16-20", detail)
        fronts = [int(c[c.index("-f") + 1]) for c in calls if c[0] == "pdftotext"]
        self.assertEqual(fronts, [1, 16])

    def test_near_empty_extraction_is_the_decline(self) -> None:
        def fake_spawn(cmd, timeout=300):
            if cmd[0] == "pdfinfo":
                return 0, "Pages:          4\n", ""
            return 0, "tiny", ""

        with mock.patch.object(plugin, "_spawn", side_effect=fake_spawn):
            isbn, detail = plugin.scan_pdf(
                Path("book.pdf"), plugin.DEFAULT_ISBN13_PREFIXES
            )
        self.assertIsNone(isbn)
        self.assertIn("empty or near-empty", detail)

    def test_page_count_failure_declines(self) -> None:
        with mock.patch.object(plugin, "_spawn", return_value=(1, "", "boom")):
            isbn, detail = plugin.scan_pdf(
                Path("book.pdf"), plugin.DEFAULT_ISBN13_PREFIXES
            )
        self.assertIsNone(isbn)
        self.assertIn("page count unavailable", detail)


@unittest.skipUnless(PDF_TOOLS, "poppler not installed")
class TestPdfLive(unittest.TestCase):
    def test_rear_window_finds_page_18_of_20(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.pdf"
            filler = {
                i: f"chapter page {i} with running text so every window "
                f"clears the extraction floor of the scanner"
                for i in range(1, 21)
            }
            filler[18] = f"ISBN {GOOD_13}"
            _make_pdf(path, 20, filler)
            isbn, detail = plugin.scan_pdf(path, plugin.DEFAULT_ISBN13_PREFIXES)
            self.assertEqual(isbn, GOOD_13)
            self.assertIn("pages 16-20", detail)

    def test_front_window_finds_page_2_of_20(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.pdf"
            filler = {
                i: f"chapter page {i} with running text so every window "
                f"clears the extraction floor of the scanner"
                for i in range(1, 21)
            }
            filler[2] = f"ISBN {GOOD_13}"
            _make_pdf(path, 20, filler)
            isbn, detail = plugin.scan_pdf(path, plugin.DEFAULT_ISBN13_PREFIXES)
            self.assertEqual(isbn, GOOD_13)
            self.assertIn("pages 1-10", detail)


@unittest.skipUnless(HOST_AVAILABLE, "the calibrequarry host is not installed")
class TestVerbEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cq-eisbn-"))
        self.scratch = build_scratch(self.tmp / "scratch")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _install_format(self, book_id: int, fmt: str, source: Path) -> None:
        conn = sqlite3.connect(self.scratch)
        row = conn.execute("SELECT path FROM books WHERE id = ?", (book_id,)).fetchone()
        conn.execute(
            "INSERT INTO data (book, format, uncompressed_size, name) VALUES (?, ?, ?, ?)",
            (book_id, fmt, source.stat().st_size, "Ebook"),
        )
        conn.commit()
        conn.close()
        target = self.scratch.parent / row[0]
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target / f"Ebook.{fmt.lower()}")

    def _context(self, dry_run: bool) -> PluginContext:
        return PluginContext(
            plugin_name="extract_isbn",
            capabilities=("read", "write"),
            db_path=str(self.scratch),
            dry_run=dry_run,
        )

    def _manifest(self):
        return _load_manifest(PLUGIN_DIR / "cquarry-plugin.toml")

    def test_conflict_same_and_write_classes(self) -> None:
        # First-hit-stops means one book yields one class, so the three
        # classes need three books: book 1 (stored GOOD) conflicts, book 2
        # (seeded stored GOOD) matches, book 3 (no stored isbn) would write.
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "other.epub"
            _make_epub(other, ["<html><p>ISBN 978-0-19-501919-3</p></html>"])
            same = Path(tmp) / "same.epub"
            _make_epub(same, ["<html><p>ISBN 978-0-14-044568-8</p></html>"])
            conn = sqlite3.connect(self.scratch)
            conn.execute(
                "INSERT INTO books (title, sort, author_sort, timestamp, pubdate,"
                " has_cover, last_modified, series_index, path, uuid)"
                " VALUES ('Scratch Three', 'Three, Scratch', 'Three, Scratch',"
                " '2026-01-03 00:00:00+00:00', '2026-01-03 00:00:00+00:00', 0,"
                " '2026-01-03 00:00:00+00:00', 1.0, 'Scratch Three (3)',"
                " 'uuid-scratch-3')"
            )
            conn.execute(
                "INSERT INTO identifiers (book, type, val) VALUES (2, 'isbn', ?)",
                (GOOD_13,),
            )
            conn.commit()
            conn.close()
            self._install_format(1, "EPUB", other)
            self._install_format(2, "EPUB", same)
            self._install_format(3, "EPUB", same)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = run_plugin_verb(
                    self._manifest(), self._context(True), ["scan", "--ids", "1,2,3"]
                )
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        self.assertIn("CONFLICT", out)
        self.assertIn("same isbn stored", out)
        self.assertIn("changed ids: 3", out)

    def test_dry_run_reports_and_apply_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "book.epub"
            _make_epub(fixture, ["<html><p>ISBN 978-0-14-044568-8</p></html>"])
            self._install_format(2, "EPUB", fixture)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = run_plugin_verb(
                    self._manifest(), self._context(True), ["scan", "--ids", "2"]
                )
        self.assertEqual(code, 0)
        self.assertIn(f"found {GOOD_13}", buffer.getvalue())
        self.assertIn("changed ids: 2", buffer.getvalue())
        conn = sqlite3.connect(self.scratch)
        stored = conn.execute(
            "SELECT val FROM identifiers WHERE book = 2 AND type = 'isbn'"
        ).fetchone()
        conn.close()
        self.assertIsNone(stored, "dry run must not write")

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run_plugin_verb(
                self._manifest(), self._context(False), ["scan", "--ids", "2"]
            )
        self.assertEqual(code, 0)
        self.assertIn("applied 1 identifier write(s)", buffer.getvalue())
        conn = sqlite3.connect(self.scratch)
        stored = conn.execute(
            "SELECT val FROM identifiers WHERE book = 2 AND type = 'isbn'"
        ).fetchone()
        conn.close()
        self.assertEqual(stored[0], GOOD_13)

    def test_no_formats_declines(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run_plugin_verb(
                self._manifest(), self._context(True), ["scan", "--ids", "1"]
            )
        self.assertEqual(code, 0)
        self.assertIn("no formats on the book", buffer.getvalue())

    def test_host_verify_passes_with_the_probe(self) -> None:
        report, manifest, _digest = verify(PLUGIN_DIR)
        self.assertTrue(report.ok, report.lines)
        self.assertEqual(manifest.name, "extract_isbn")
        self.assertTrue(
            any("probe 'scan --ids 1' exited 0" in line for line in report.lines)
        )


if __name__ == "__main__":
    unittest.main()
