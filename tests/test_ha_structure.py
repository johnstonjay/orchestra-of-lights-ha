"""Repository & Home Assistant metadata / structure regression tests."""

from __future__ import annotations

import json
import py_compile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMP = ROOT / "custom_components" / "orchestra_of_lights"


class TestHomeAssistantStructure(unittest.TestCase):
    """Validate manifest, HACS config, translations parity, and Python syntax."""

    def test_manifest_valid_and_hassfest_key_order(self) -> None:
        manifest = json.loads((COMP / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], "orchestra_of_lights")
        self.assertTrue(manifest["config_flow"])
        self.assertEqual(manifest["requirements"], [])
        self.assertIn("version", manifest)
        # Hassfest requires domain, name, then remaining keys sorted alphabetically
        keys = list(manifest.keys())
        self.assertEqual(keys[:2], ["domain", "name"])
        self.assertEqual(keys[2:], sorted(keys[2:]))

    def test_hacs_json(self) -> None:
        hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))
        self.assertIn("name", hacs)

    def test_strings_and_en_translation_parity(self) -> None:
        strings = json.loads((COMP / "strings.json").read_text(encoding="utf-8"))
        en = json.loads((COMP / "translations" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(strings, en)

    def test_all_python_files_compile(self) -> None:
        py_files = list(COMP.glob("*.py")) + [ROOT / "ool_cli.py"]
        self.assertGreaterEqual(len(py_files), 10)
        for py_file in py_files:
            py_compile.compile(str(py_file), doraise=True)

    def test_yaml_files_parse(self) -> None:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError:
            self.skipTest("PyYAML not installed in local test environment")
        yaml_files = [COMP / "services.yaml"] + list((ROOT / "examples").glob("*.yaml"))
        for yfile in yaml_files:
            data = yaml.safe_load(yfile.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict, f"Expected dict in {yfile}")


if __name__ == "__main__":
    unittest.main()
