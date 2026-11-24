"""The find_duplicates port's suite: matcher units, the grouping pipeline,
and the verbs end to end over scratch libraries.

Matcher expectations are ported from upstream's own self-test suite
(matching.py's calibre-debug block) and its recorded behaviors; the
exemption-partition case is the one documented in upstream's partition
comment. The end-to-end tests run the loaded plugin through the host's
harness against scratch libraries seeded with duplicate-shaped books.
"""

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
except ImportError:  # pragma: no cover - CI installs the host before the suite
    HOST_AVAILABLE = False


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "cquarry_plugin_find_duplicates_test", PLUGIN_DIR / "plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plugin = _load_plugin()


class TestMatcherLadder(unittest.TestCase):
    def test_soundex_classic_pair(self) -> None:
        self.assertEqual(plugin._soundex("Robert", 4), "R163")
        self.assertEqual(plugin._soundex("Rupert", 4), "R163")

    def test_fuzzy_title_strips_and_truncates(self) -> None:
        # the "and" tail truncates aggressively (upstream's rule): both
        # shapes reduce to "design"; the edition paren drops with the tail
        self.assertEqual(
            plugin.fuzzy_title_match("The Design and Evolution of C++"), "design"
        )
        self.assertEqual(
            plugin.fuzzy_title_match("Design and Evolution of C++, The (2nd Edition)"),
            "design",
        )

    def test_similar_title_automerge_strip(self) -> None:
        # a TRUE pair under the strip: the leading-article rule runs once,
        # so "The: A Novel" does NOT match "A Novel" upstream either
        self.assertEqual(
            plugin.similar_title_match("The Design Patterns"),
            plugin.similar_title_match("Design Patterns"),
        )
        self.assertEqual(
            plugin.similar_title_match("Design!, the"), "design! the"
        )  # ! stays (upstream class)

    def test_author_tokens_rotate_comma_form(self) -> None:
        similar, rev = plugin.similar_authors_match("Anderson, Kevin J.")
        self.assertEqual(similar, "kevin anderson")  # the initial J. strips
        self.assertEqual(rev, "anderson kevin")
        name, rev2 = plugin.similar_authors_match("Kevin J. Anderson")
        self.assertEqual(name, "kevin anderson")
        self.assertEqual(rev2, "anderson kevin")

    def test_author_order_free_match(self) -> None:
        a = plugin.similar_authors_match("Anderson, Kevin")
        b = plugin.similar_authors_match("Kevin Anderson")
        self.assertTrue(a[0] in b or a[1] in b or a[0] == b[0])

    def test_fuzzy_author_initial_rule(self) -> None:
        self.assertEqual(plugin.fuzzy_authors_match("Bronte, A."), ("abronte", None))
        self.assertEqual(plugin.fuzzy_authors_match("A. Bronte"), ("abronte", None))

    def test_author_ignore_words_drop(self) -> None:
        tokens = list(plugin._get_author_tokens("Ursula von der Leyen"))
        self.assertNotIn("von", tokens)


class TestGrouping(unittest.TestCase):
    def test_subset_groups_removed(self) -> None:
        candidates = {"a": {1, 2}, "b": {1, 2, 3}}
        self.assertEqual(plugin._clean_dup_groups(candidates), [{1, 2, 3}])

    def test_shrink_drops_singletons(self) -> None:
        candidates = {"a": {1}, "b": {2, 3}}
        plugin._shrink(candidates)
        self.assertEqual(list(candidates), ["b"])

    def test_partition_with_the_upstream_comment_case(self) -> None:
        # (1,2,3,4) with non-dups [(1,2),(2,3)]: the documented subtlety
        # yields (1,3,4) and (2,4), never the subset (3,4).
        emap = plugin.ExemptionMap([[1, 2], [2, 3]])
        self.assertEqual(
            plugin._partition_using_exemptions([1, 2, 3, 4], emap), [[1, 3, 4], [2, 4]]
        )

    def test_partition_without_exemptions_keeps_the_group(self) -> None:
        emap = plugin.ExemptionMap([])
        self.assertEqual(
            plugin._partition_using_exemptions([1, 2, 3], emap), [[1, 2, 3]]
        )


def _seed_library(db_path, books):
    """books: list of (title, authors list, isbn or None)."""
    conn = sqlite3.connect(db_path)
    try:
        for title, authors, isbn in books:
            conn.execute(
                "INSERT INTO books (title, sort, author_sort, timestamp, pubdate,"
                " has_cover, last_modified, series_index, path, uuid)"
                " VALUES (?, ?, ?, '2026-01-01', '2026-01-01', 0,"
                " '2026-01-01', 1.0, ?, ?)",
                (
                    title,
                    title,
                    ", ".join(authors),
                    f"{title[:20].replace(' ', '_')} ({conn.execute('SELECT COUNT(*) FROM books').fetchone()[0] + 1})",
                    f"uuid-{title[:12]}-{conn.execute('SELECT COUNT(*) FROM books').fetchone()[0] + 1}",
                ),
            )
            book_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for author in authors:
                row = conn.execute(
                    "SELECT id FROM authors WHERE name = ?", (author,)
                ).fetchone()
                aid = row[0] if row else None
                if aid is None:
                    conn.execute(
                        "INSERT INTO authors (name, sort) VALUES (?, ?)",
                        (author, author),
                    )
                    aid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    "INSERT INTO books_authors_link (book, author) VALUES (?, ?)",
                    (book_id, aid),
                )
            if isbn:
                conn.execute(
                    "INSERT INTO identifiers (book, type, val) VALUES (?, 'isbn', ?)",
                    (book_id, isbn),
                )
        conn.commit()
    finally:
        conn.close()


@unittest.skipUnless(HOST_AVAILABLE, "the calibrequarry host is not installed")
class TestVerbs(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cq-fdup-"))
        self.scratch = build_scratch(self.tmp / "lib")
        self._clean_scratch()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _clean_scratch(self) -> None:
        conn = sqlite3.connect(self.scratch)
        for table in ("books_authors_link", "books", "authors", "identifiers", "data"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        conn.close()

    def _context(self) -> PluginContext:
        return PluginContext(
            plugin_name="find_duplicates",
            capabilities=("read",),
            db_path=str(self.scratch),
            dry_run=True,
        )

    def _manifest(self):
        return _load_manifest(PLUGIN_DIR / "cquarry-plugin.toml")

    def _seed(self, books) -> None:
        _seed_library(self.scratch, books)

    def _search(self, argv) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = run_plugin_verb(self._manifest(), self._context(), argv)
        return code, buffer.getvalue()

    def test_title_author_variant_pair_groups(self) -> None:
        self._seed(
            [
                ("The Wandering Inn", ["pirateaba"], None),
                ("Wandering Inn, The", ["Pirateaba"], None),
                ("A completely unrelated book", ["Someone Else"], None),
            ]
        )
        code, out = self._search(
            ["search", "--title-match", "fuzzy", "--author-match", "fuzzy"]
        )
        self.assertEqual(code, 0)
        self.assertIn("group 1 (2 book(s))", out)
        self.assertIn("The Wandering Inn", out)
        self.assertNotIn("unrelated", out.split("summary:")[0].replace("scope:", ""))

    def test_author_reversal_matches_across_orders(self) -> None:
        self._seed(
            [
                ("Book One", ["Anderson, Kevin"], None),
                ("Book Two", ["Kevin Anderson"], None),
                ("Book Three", ["Different Author"], None),
            ]
        )
        code, out = self._search(
            ["search", "--title-match", "ignore", "--author-match", "similar"]
        )
        self.assertEqual(code, 0)
        self.assertIn("group 1 (2 book(s))", out)

    def test_fuzzy_author_initial_rule_groups(self) -> None:
        self._seed(
            [
                ("Ebook One", ["Bronte, A."], None),
                ("Ebook Two", ["A. Bronte"], None),
            ]
        )
        code, out = self._search(
            ["search", "--title-match", "ignore", "--author-match", "fuzzy"]
        )
        self.assertEqual(code, 0)
        self.assertIn("group 1 (2 book(s))", out)

    def test_identifier_exact_equality_only(self) -> None:
        self._seed(
            [
                ("Book One", ["Author A"], "978-0-14-044568-8"),
                ("Book Two", ["Author B"], "9780140445688"),
                ("Book Three", ["Author C"], "9780140445688"),
            ]
        )
        code, out = self._search(
            ["search", "--type", "identifier", "--identifier-type", "isbn"]
        )
        self.assertEqual(code, 0)
        self.assertIn("group 1 (2 book(s))", out)
        self.assertIn("Book Two", out.split("group")[1])
        self.assertIn("Book Three", out.split("group")[1])
        self.assertNotIn("Book One", out.split("group")[1])

    def test_binary_groups_byte_identical_formats(self) -> None:
        self._seed(
            [
                ("Book One", ["Author A"], None),
                ("Book Two", ["Author B"], None),
                ("Book Three", ["Author C"], None),
            ]
        )
        payload = b"a very particular ebook payload" * 100
        other = b"something else entirely" * 90
        conn = sqlite3.connect(self.scratch)
        ids = [
            r[0] for r in conn.execute("SELECT id FROM books ORDER BY id").fetchall()
        ]
        targets = [(ids[0], payload), (ids[1], payload), (ids[2], other)]
        for book_id, data in targets:
            row = conn.execute(
                "SELECT path FROM books WHERE id = ?", (book_id,)
            ).fetchone()
            conn.execute(
                "INSERT INTO data (book, format, uncompressed_size, name) VALUES (?, 'EPUB', ?, 'E')",
                (book_id, len(data)),
            )
            d = self.scratch.parent / row[0]
            d.mkdir(parents=True, exist_ok=True)
            (d / "E.epub").write_bytes(data)
        conn.commit()
        conn.close()
        code, out = self._search(["search", "--type", "binary"])
        self.assertEqual(code, 0)
        self.assertIn("group 1 (2 book(s))", out)
        self.assertIn("Book One", out.split("group")[1])
        self.assertIn("Book Two", out.split("group")[1])
        self.assertNotIn("Book Three", out.split("group")[1])

    def test_exempt_removes_a_pair_and_comeback(self) -> None:
        self._seed(
            [
                ("Same Title", ["Author"], None),
                ("Same Title", ["Author"], None),
            ]
        )
        code, out = self._search(["search", "--title-match", "identical"])
        self.assertIn("group 1 (2 book(s))", out)
        import re as _re

        with contextlib.redirect_stdout(io.StringIO()):
            code = run_plugin_verb(
                self._manifest(),
                self._context(),
                ["exempt", "--books", ",".join(_re.findall(r"#(\d+) ", out))],
            )
        self.assertEqual(code, 0)
        code, out = self._search(["search", "--title-match", "identical"])
        self.assertNotIn("group 1", out)
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            run_plugin_verb(self._manifest(), self._context(), ["exempt", "--list"])
        self.assertIn("[0]", buffer.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            code = run_plugin_verb(
                self._manifest(), self._context(), ["exempt", "--remove", "0"]
            )
        self.assertEqual(code, 0)
        code, out = self._search(["search", "--title-match", "identical"])
        self.assertIn("group 1 (2 book(s))", out)

    def test_json_shape_carries_upstream_fields(self) -> None:
        self._seed(
            [
                ("Same Title", ["Author"], None),
                ("Same Title", ["Author"], None),
            ]
        )
        code, out = self._search(["search", "--format", "json"])
        import json

        payload = json.loads(out)
        self.assertIn("books_for_group", payload)
        self.assertIn("library_path", payload)
        self.assertIn("timestamp", payload)
        self.assertIn("entangled_groups_for_book", payload)

    def test_cross_library_reports_matches(self) -> None:
        self._seed([("The Same Book", ["Same Author"], "9780140445688")])
        other = build_scratch(self.tmp / "other")
        conn = sqlite3.connect(other)
        conn.execute("DELETE FROM books")
        conn.execute("DELETE FROM authors")
        conn.commit()
        conn.close()
        _seed_library(other, [("The Same Book", ["Same Author"], "9780140445688")])
        code, out = self._search(["search", "--against", str(other)])
        self.assertEqual(code, 0)
        self.assertIn("cross-library", out)
        self.assertIn("== target", out)
        self.assertIn("The Same Book", out)

    def test_title_ignore_identical_author_refused(self) -> None:
        self._seed([("Anything", ["Author"], None)])
        code, out = self._search(
            ["search", "--title-match", "ignore", "--author-match", "identical"]
        )
        self.assertEqual(code, 2)

    def test_host_verify_passes_with_probes(self) -> None:
        report, manifest, _digest = verify(PLUGIN_DIR)
        self.assertTrue(report.ok, report.lines)
        self.assertEqual(manifest.name, "find_duplicates")
        self.assertEqual(manifest.api_version, 2)
        self.assertTrue(
            any(
                "probe 'search --type identifier' exited 0" in line
                for line in report.lines
            )
        )
        self.assertTrue(
            any("probe 'exempt --list' exited 0" in line for line in report.lines)
        )


if __name__ == "__main__":
    unittest.main()
