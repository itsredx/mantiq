# ── Imports ─────────────────────────────────────────────────────────────
import os
import sys
import shutil
import tempfile
import unittest
import json

from nizam.transpiler.project import ProjectTranspiler, transpile_project
from nizam.transpiler.cli import main as cli_main

# ── Project Transpiler Test Suite ───────────────────────────────────────
class TestProjectTranspiler(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="nizam_proj_test_")
        self.src_dir = os.path.join(self.temp_dir, "src_project")
        self.out_dir = os.path.join(self.temp_dir, "out_project")
        os.makedirs(self.src_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_directory_structure_preserved(self):
        """Verify nested subpackages and files map 1:1 in the transpiled directory."""
        # Create nested package structure
        sub_dir = os.path.join(self.src_dir, "pkg", "subpkg")
        os.makedirs(sub_dir, exist_ok=True)

        with open(os.path.join(sub_dir, "math_utils.py"), "w") as f:
            f.write("def add(a: int, b: int) -> int:\n    return a + b\n")

        with open(os.path.join(self.src_dir, "pkg", "models.py"), "w") as f:
            f.write("class Item:\n    def __init__(self, val: int):\n        self.val = val\n")

        with open(os.path.join(self.src_dir, "app.py"), "w") as f:
            f.write("from pkg.subpkg.math_utils import add\ndef run() -> int:\n    return add(10, 20)\n")

        transpiler = ProjectTranspiler(
            source_dir=self.src_dir,
            output_dir=self.out_dir,
            syntax="nz",
        )
        manifest = transpiler.execute()

        # Check file existence in output directory
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, "pkg", "subpkg", "math_utils.nz")))
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, "pkg", "models.nz")))
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, "app.nz")))

        # Verify summary stats
        self.assertEqual(manifest["summary"]["scanned_python"], 3)
        self.assertEqual(manifest["summary"]["transpiled_success"], 3)
        self.assertEqual(manifest["summary"]["transpiled_fallback"], 0)

    def test_cython_so_and_pyx_detected_and_bridged(self):
        """Verify Cython .so/.pyx detection, binary replication, and FFI bridge synthesis."""
        engine_dir = os.path.join(self.src_dir, "engine")
        os.makedirs(engine_dir, exist_ok=True)

        # Mock Cython .pyx source
        pyx_content = (
            "def diff_trees(old_tree, new_tree):\n"
            "    return []\n\n"
            "cdef class PatchNode:\n"
            "    cdef public int id\n"
        )
        with open(os.path.join(engine_dir, "reconciler_cython.pyx"), "w") as f:
            f.write(pyx_content)

        # Mock compiled .so file
        with open(os.path.join(engine_dir, "reconciler_cython.cpython-312-x86_64-linux-gnu.so"), "wb") as f:
            f.write(b"\x7fELFfake_so_content")

        with open(os.path.join(engine_dir, "service.py"), "w") as f:
            f.write("def start() -> int:\n    return 0\n")

        transpiler = ProjectTranspiler(
            source_dir=self.src_dir,
            output_dir=self.out_dir,
            syntax="nz",
            copy_extensions=True,
            bridge_cython=True,
        )
        manifest = transpiler.execute()

        # Check .so was copied
        out_so = os.path.join(self.out_dir, "engine", "reconciler_cython.cpython-312-x86_64-linux-gnu.so")
        self.assertTrue(os.path.isfile(out_so))

        # Check synthesized bridge file
        bridge_file = os.path.join(self.out_dir, "engine", "reconciler_cython.nz")
        self.assertTrue(os.path.isfile(bridge_file))

        with open(bridge_file, "r") as f:
            bridge_code = f.read()

        self.assertIn("extern[python] fn diff_trees", bridge_code)
        self.assertIn("struct PatchNode:", bridge_code)
        self.assertEqual(manifest["summary"]["bridged_cython_modules"], 1)

    def test_asset_replication(self):
        """Verify non-Python assets (.json, .yaml, .txt) are copied faithfully."""
        assets_dir = os.path.join(self.src_dir, "assets")
        os.makedirs(assets_dir, exist_ok=True)

        config_data = {"version": "1.0.0", "name": "demo_test"}
        with open(os.path.join(assets_dir, "config.json"), "w") as f:
            json.dump(config_data, f)

        with open(os.path.join(assets_dir, "theme.yaml"), "w") as f:
            f.write("theme: dark\naccent: cyan\n")

        with open(os.path.join(self.src_dir, "index.py"), "w") as f:
            f.write("def main() -> int:\n    return 0\n")

        transpiler = ProjectTranspiler(
            source_dir=self.src_dir,
            output_dir=self.out_dir,
            copy_assets=True,
        )
        manifest = transpiler.execute()

        out_json = os.path.join(self.out_dir, "assets", "config.json")
        out_yaml = os.path.join(self.out_dir, "assets", "theme.yaml")
        self.assertTrue(os.path.isfile(out_json))
        self.assertTrue(os.path.isfile(out_yaml))

        with open(out_json, "r") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["version"], "1.0.0")
        self.assertEqual(manifest["summary"]["copied_assets"], 2)

    def test_compiler_check_mode(self):
        """Verify compiler check mode validates generated code without full build."""
        with open(os.path.join(self.src_dir, "valid.py"), "w") as f:
            f.write(
                "def compute(a: int, b: int) -> int:\n"
                "    return a + b\n"
            )

        transpiler = ProjectTranspiler(
            source_dir=self.src_dir,
            output_dir=self.out_dir,
            syntax="nz",
            check=True,
        )
        manifest = transpiler.execute()

        # If compiler binary was found, check should pass
        if transpiler.mantiq_bin:
            self.assertEqual(manifest["summary"]["check_failed"], 0)
            self.assertGreaterEqual(manifest["summary"]["check_passed"], 1)

    def test_cli_project_transpilation(self):
        """Verify CLI entrypoint supports --project with --check and --report."""
        with open(os.path.join(self.src_dir, "entry.py"), "w") as f:
            f.write("def main() -> int:\n    return 42\n")

        ret = cli_main(["--project", self.src_dir, "-o", self.out_dir, "--syntax", "nz", "--check"])
        self.assertEqual(ret, 0)

        # Manifest and Report should exist
        manifest_file = os.path.join(self.out_dir, "transpile_manifest.json")
        report_file = os.path.join(self.out_dir, "TRANSPILATION_REPORT.md")
        self.assertTrue(os.path.isfile(manifest_file))
        self.assertTrue(os.path.isfile(report_file))

        with open(report_file, "r") as f:
            report_text = f.read()
        self.assertIn("Nizam Project Transpilation Report", report_text)
        self.assertIn("Summary Statistics", report_text)

    def test_mantiq_syntax_mode(self):
        """Verify --syntax mq emits .mq extension files."""
        with open(os.path.join(self.src_dir, "widget.py"), "w") as f:
            f.write("def draw() -> int:\n    return 1\n")

        transpile_project(
            source_dir=self.src_dir,
            output_dir=self.out_dir,
            syntax="mq",
        )

        out_mq = os.path.join(self.out_dir, "widget.mq")
        self.assertTrue(os.path.isfile(out_mq))

if __name__ == "__main__":
    unittest.main()
