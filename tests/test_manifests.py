"""The manifest lint: every plugin directory carries a valid cquarry-plugin.toml.

Structure only, never values: the floors are re-pinned by the ports that use
the newer surface (spec.md, the version-floors section).
"""

import re
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN_DIRS = ("extract_isbn", "find_duplicates", "quality_check")
CAPABILITIES = {"read", "write", "network"}
DERIVATIONS = {"port", "clean-room", "original"}
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
FLOOR_RE = re.compile(r"^>=\d+(\.\d+){0,2}$")
ENTRY_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)
UPSTREAM_SOURCE = "https://github.com/kiwidude68/calibre_plugins"


def _load_manifest(plugin_dir: str) -> dict:
    path = REPO / plugin_dir / "cquarry-plugin.toml"
    with path.open("rb") as fh:
        return tomllib.load(fh)


class TestManifestContract(unittest.TestCase):
    def test_every_plugin_dir_has_a_manifest(self) -> None:
        for plugin_dir in PLUGIN_DIRS:
            path = REPO / plugin_dir / "cquarry-plugin.toml"
            self.assertTrue(path.is_file(), f"missing manifest: {path}")

    def test_names_are_unique_and_match_their_dirs(self) -> None:
        names = []
        for plugin_dir in PLUGIN_DIRS:
            manifest = _load_manifest(plugin_dir)
            self.assertEqual(
                manifest["name"],
                plugin_dir,
                f"name must equal its directory: {plugin_dir}",
            )
            names.append(manifest["name"])
        self.assertEqual(len(names), len(set(names)), "plugin names must be unique")

    def test_core_fields(self) -> None:
        for plugin_dir in PLUGIN_DIRS:
            manifest = _load_manifest(plugin_dir)
            with self.subTest(plugin=plugin_dir):
                self.assertEqual(manifest["schema"], 1)
                self.assertIsInstance(manifest["api_version"], int)
                self.assertGreaterEqual(manifest["api_version"], 1)
                self.assertRegex(manifest["version"], VERSION_RE)
                self.assertEqual(manifest["license"], "GPL-3.0-only")
                self.assertRegex(manifest["entry"], ENTRY_RE)
                self.assertIsInstance(manifest["description"], str)
                self.assertTrue(manifest["description"].strip())

    def test_capabilities_are_known_and_nonempty(self) -> None:
        for plugin_dir in PLUGIN_DIRS:
            manifest = _load_manifest(plugin_dir)
            with self.subTest(plugin=plugin_dir):
                caps = manifest["capabilities"]
                self.assertIsInstance(caps, list)
                self.assertTrue(caps, "a plugin declares at least one capability")
                self.assertTrue(
                    set(caps).issubset(CAPABILITIES), f"unknown capability: {caps}"
                )

    def test_version_floors_are_declared(self) -> None:
        for plugin_dir in PLUGIN_DIRS:
            manifest = _load_manifest(plugin_dir)
            with self.subTest(plugin=plugin_dir):
                requires = manifest["requires"]
                self.assertRegex(requires["cquarry"], FLOOR_RE)
                self.assertRegex(requires["calibrequarry"], FLOOR_RE)

    def test_upstream_provenance(self) -> None:
        for plugin_dir in PLUGIN_DIRS:
            manifest = _load_manifest(plugin_dir)
            with self.subTest(plugin=plugin_dir):
                upstream = manifest["upstream"]
                self.assertEqual(upstream["source"], UPSTREAM_SOURCE)
                self.assertEqual(upstream["plugin"], plugin_dir)
                self.assertRegex(upstream["version"], VERSION_RE)
                self.assertEqual(upstream["license"], "GPL-3.0")
                self.assertIn(upstream["derivation"], DERIVATIONS)

    def test_every_plugin_has_a_provenance_readme(self) -> None:
        for plugin_dir in PLUGIN_DIRS:
            readme = (REPO / plugin_dir / "README.md").read_text(encoding="utf-8")
            with self.subTest(plugin=plugin_dir):
                self.assertIn(UPSTREAM_SOURCE, readme)
                self.assertIn("GPL-3", readme)


if __name__ == "__main__":
    unittest.main()
