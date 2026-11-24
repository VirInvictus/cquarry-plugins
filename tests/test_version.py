"""The version-sync pin: VERSION == pyproject == the newest patchnotes heading."""

import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _repo_version() -> str:
    return (REPO / "VERSION").read_text(encoding="utf-8").strip()


def _pyproject_version() -> str:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def _patchnotes_version() -> str:
    for line in (REPO / "patchnotes.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## v"):
            return line.removeprefix("## v").strip()
    raise AssertionError("patchnotes.md carries no '## vX.Y.Z' heading")


class TestVersionSync(unittest.TestCase):
    def test_all_carriers_agree(self) -> None:
        version = _repo_version()
        self.assertEqual(version, _pyproject_version())
        self.assertEqual(version, _patchnotes_version())

    def test_version_is_semver(self) -> None:
        parts = _repo_version().split(".")
        self.assertEqual(len(parts), 3, "VERSION must be X.Y.Z")
        for part in parts:
            self.assertTrue(part.isdigit(), f"non-numeric version part: {part}")


if __name__ == "__main__":
    unittest.main()
