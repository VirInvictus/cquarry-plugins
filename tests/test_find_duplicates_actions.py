"""The find_duplicates actions suite: merge, duplicate-format removal,
deletion, and the variations/rename pair -- every action through the
host's gates over scratch libraries with REAL format files (the file
copies are the layer mocks cannot cover; the live-seam lesson)."""

import contextlib
import importlib.util
import io
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO / "find_duplicates"

try:
    from cquarry_cli.plugins.gates import PluginContext
    from cquarry_cli.plugins.harness import verify
    from cquarry_cli.plugins.manifest import load_manifest as _load_manifest
    from cquarry_cli.plugins.scratch import build_scratch
    from cquarry_cli.plugins.verbs import run_plugin_verb

    HOST_AVAILABLE = True
except ImportError:  # pragma: no cover
    HOST_AVAILABLE = False


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "cquarry_plugin_find_duplicates_actions", PLUGIN_DIR / "plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plugin = _load_plugin()


def _seed_library(db_path, books):
    """books: list of (title, authors list, publisher or None)."""
    conn = sqlite3.connect(db_path)
    try:
        for title, authors, publisher in books:
            conn.execute(
                "INSERT INTO books (title, sort, author_sort, timestamp, pubdate,"
                " has_cover, last_modified, series_index, path, uuid)"
                " VALUES (?, ?, ?, '2026-01-01', '2026-01-01', 0,"
                " '2026-01-01', 1.0, ?, ?)",
                (
                    title,
                    title,
                    ", ".join(authors),
                    f"p{title[:10].replace(' ', '_')}"
                    f"{conn.execute('SELECT COUNT(*) FROM books').fetchone()[0] + 1}",
                    f"uuid-{title[:10]}-{conn.execute('SELECT COUNT(*) FROM books').fetchone()[0]}",
                ),
            )
            book_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for author in authors:
                row = conn.execute(
                    "SELECT id FROM authors WHERE name = ?", (author,)
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO authors (name, sort) VALUES (?, ?)",
                        (author, author),
                    )
                    aid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    aid = row[0]
                conn.execute(
                    "INSERT INTO books_authors_link (book, author) VALUES (?, ?)",
                    (book_id, aid),
                )
            if publisher:
                row = conn.execute(
                    "SELECT id FROM publishers WHERE name = ?", (publisher,)
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO publishers (name) VALUES (?)", (publisher,)
                    )
                    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                else:
                    pid = row[0]
                conn.execute(
                    "INSERT INTO books_publishers_link (book, publisher) VALUES (?, ?)",
                    (book_id, pid),
                )
        conn.commit()
    finally:
        conn.close()


def _install_format(db_path, book_id, fmt, payload: bytes, stem="Ebook") -> Path:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT path FROM books WHERE id = ?", (book_id,)).fetchone()
    conn.execute(
        "INSERT INTO data (book, format, uncompressed_size, name) VALUES (?, ?, ?, ?)",
        (book_id, fmt, len(payload), stem),
    )
    conn.commit()
    conn.close()
    d = db_path.parent / row[0]
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{stem}.{fmt.lower()}"
    f.write_bytes(payload)
    return f


@unittest.skipUnless(HOST_AVAILABLE, "the calibrequarry host is not installed")
class TestActions(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cq-fdup-actions-"))
        self.scratch = build_scratch(self.tmp / "lib")
        conn = sqlite3.connect(self.scratch)
        for table in ("books_authors_link", "books", "authors", "identifiers", "data"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _context(self, apply: bool) -> PluginContext:
        return PluginContext(
            plugin_name="find_duplicates",
            capabilities=("read", "write"),
            db_path=str(self.scratch),
            dry_run=not apply,
        )

    def _manifest(self):
        return _load_manifest(PLUGIN_DIR / "cquarry-plugin.toml")

    def _run(self, argv, apply=False) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run_plugin_verb(self._manifest(), self._context(apply), argv)
        return code, buffer.getvalue()

    def _db(self):
        return sqlite3.connect(self.scratch)

    def test_merge_dry_run_touches_nothing(self) -> None:
        _seed_library(
            self.scratch,
            [
                ("Keeper Book", ["Keeper Author"], "Keeper Press"),
                ("Dup Book", ["Dup Author"], "Dup Press"),
            ],
        )
        conn = self._db()
        keeper = conn.execute(
            "SELECT id FROM books WHERE title = 'Keeper Book'"
        ).fetchone()[0]
        dup = conn.execute("SELECT id FROM books WHERE title = 'Dup Book'").fetchone()[
            0
        ]
        conn.close()
        payload = b"the dup book payload" * 50
        _install_format(self.scratch, dup, "EPUB", payload)
        code, out = self._run(
            ["merge", "--keeper", str(keeper), "--ids", str(dup)], apply=False
        )
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", out)
        self.assertIn("copy", out)
        self.assertIn(f"remove #{dup}", out)
        conn = self._db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM books").fetchone()[0], 2)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM data").fetchone()[0], 1)
        conn.close()

    def test_merge_moves_formats_fills_and_removes(self) -> None:
        _seed_library(
            self.scratch,
            [
                # the keeper carries NO publisher: the merge's fill-blank
                # adopts the source's (a keeper value would win)
                ("Keeper Book", ["Keeper Author"], None),
                ("Dup Book", ["Dup Author"], "Dup Press"),
            ],
        )
        conn = self._db()
        keeper = conn.execute(
            "SELECT id FROM books WHERE title = 'Keeper Book'"
        ).fetchone()[0]
        dup = conn.execute("SELECT id FROM books WHERE title = 'Dup Book'").fetchone()[
            0
        ]
        conn.close()
        payload = b"the dup book payload" * 50
        _install_format(self.scratch, dup, "EPUB", payload)
        _install_format(self.scratch, keeper, "MOBI", b"keeper mobi" * 40, stem="Kep")
        code, out = self._run(
            [
                "merge",
                "--keeper",
                str(keeper),
                "--ids",
                str(dup),
                "--fields",
                "authors,publisher,comments",
            ],
            apply=True,
        )
        self.assertEqual(code, 0)
        self.assertIn("applied", out)
        conn = self._db()
        self.assertEqual(
            [r[0] for r in conn.execute("SELECT title FROM books").fetchall()],
            ["Keeper Book"],
        )
        keeper_fmts = sorted(
            r[0]
            for r in conn.execute(
                "SELECT format FROM data WHERE book = ?", (keeper,)
            ).fetchall()
        )
        self.assertEqual(keeper_fmts, ["EPUB", "MOBI"])
        # the copied payload exists at the keeper's format file (resolve via
        # the engine: the author re-lay may have renamed the file)
        context = self._context(True)
        epub_path = context.format_paths(keeper)["EPUB"]
        self.assertTrue(epub_path.exists())
        self.assertEqual(epub_path.read_bytes(), payload)
        # the publisher filled from the source; authors unioned
        pub = conn.execute(
            "SELECT p.name FROM books_publishers_link bl"
            " JOIN publishers p ON p.id = bl.publisher WHERE bl.book = ?",
            (keeper,),
        ).fetchall()
        self.assertEqual([r[0] for r in pub], ["Dup Press"])
        authors = [
            r[0]
            for r in conn.execute(
                "SELECT a.name FROM books_authors_link bl"
                " JOIN authors a ON a.id = bl.author WHERE bl.book = ?",
                (keeper,),
            ).fetchall()
        ]
        self.assertEqual(sorted(authors), ["Dup Author", "Keeper Author"])
        conn.close()

    def test_merge_conflicting_isbn_never_overwrites(self) -> None:
        _seed_library(
            self.scratch,
            [
                ("Keeper Book", ["Keeper Author"], None),
                ("Dup Book", ["Dup Author"], None),
            ],
        )
        conn = self._db()
        keeper = conn.execute(
            "SELECT id FROM books WHERE title = 'Keeper Book'"
        ).fetchone()[0]
        dup = conn.execute("SELECT id FROM books WHERE title = 'Dup Book'").fetchone()[
            0
        ]
        conn.execute(
            "INSERT INTO identifiers (book, type, val) VALUES (?, 'isbn', 'A')",
            (keeper,),
        )
        conn.execute(
            "INSERT INTO identifiers (book, type, val) VALUES (?, 'isbn', 'B')",
            (dup,),
        )
        conn.commit()
        conn.close()
        code, out = self._run(
            [
                "merge",
                "--keeper",
                str(keeper),
                "--ids",
                str(dup),
                "--fields",
                "identifiers",
            ],
            apply=True,
        )
        self.assertEqual(code, 0)
        self.assertIn("CONFLICT", out)
        conn = self._db()
        self.assertEqual(
            conn.execute(
                "SELECT val FROM identifiers WHERE book = ? AND type = 'isbn'",
                (keeper,),
            ).fetchone()[0],
            "A",
        )
        conn.close()

    def test_remove_duplicate_formats_keeps_earliest(self) -> None:
        _seed_library(
            self.scratch,
            [
                ("Book One", ["Author"], None),
                ("Book Two", ["Author"], None),
            ],
        )
        payload = b"byte identical payload" * 100
        f1 = _install_format(self.scratch, 3, "EPUB", payload, stem="One")
        _install_format(self.scratch, 4, "EPUB", payload, stem="Two")
        import os

        os.utime(f1, (1000000, 1000000))  # book 3's copy is older
        code, out = self._run(["remove-duplicate-formats", "--ids", "3,4"], apply=True)
        self.assertEqual(code, 0)
        conn = self._db()
        remaining = [
            r[0]
            for r in conn.execute(
                "SELECT book FROM data WHERE format = 'EPUB'"
            ).fetchall()
        ]
        conn.close()
        self.assertEqual(remaining, [3])  # book 4's duplicate format removed

    def test_delete_removes_named_rows(self) -> None:
        _seed_library(
            self.scratch,
            [
                ("Doomed", ["Author"], None),
                ("Survivor", ["Author"], None),
            ],
        )
        conn = self._db()
        doomed = conn.execute("SELECT id FROM books WHERE title = 'Doomed'").fetchone()[
            0
        ]
        conn.close()
        code, out = self._run(["delete", "--ids", str(doomed)], apply=True)
        self.assertEqual(code, 0)
        conn = self._db()
        self.assertEqual(
            [r[0] for r in conn.execute("SELECT title FROM books").fetchall()],
            ["Survivor"],
        )
        conn.close()

    def test_variations_report_and_rename(self) -> None:
        _seed_library(
            self.scratch,
            [
                ("Book One", ["Kevin Anderson"], None),
                ("Book Two", ["Anderson, Kevin"], None),
                ("Book Three", ["Unrelated Author"], None),
            ],
        )
        code, out = self._run(["variations", "--item", "authors", "--match", "fuzzy"])
        self.assertEqual(code, 0)
        self.assertIn("Kevin Anderson", out)
        code, out = self._run(
            [
                "rename",
                "--kind",
                "authors",
                "--from",
                "Anderson, Kevin",
                "--to",
                "Kevin Anderson",
            ],
            apply=True,
        )
        self.assertEqual(code, 0)
        conn = self._db()
        names = [r[0] for r in conn.execute("SELECT name FROM authors").fetchall()]
        conn.close()
        self.assertNotIn("Anderson, Kevin", names)
        self.assertIn("Kevin Anderson", names)

    def test_actions_are_dry_by_default(self) -> None:
        _seed_library(
            self.scratch,
            [
                ("Doomed", ["Author"], None),
                ("Survivor", ["Author"], None),
            ],
        )
        conn = self._db()
        doomed = conn.execute("SELECT id FROM books WHERE title = 'Doomed'").fetchone()[
            0
        ]
        conn.close()
        code, out = self._run(["delete", "--ids", str(doomed)], apply=False)
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", out)
        conn = self._db()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM books").fetchone()[0], 2)
        conn.close()

    def test_host_verify_still_passes(self) -> None:
        report, manifest, _digest = verify(PLUGIN_DIR)
        self.assertTrue(report.ok, report.lines)
        self.assertEqual(manifest.version, "0.4.1")


if __name__ == "__main__":
    unittest.main()
