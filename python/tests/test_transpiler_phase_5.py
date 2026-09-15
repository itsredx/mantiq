# ── Imports ─────────────────────────────────────────────────────────────
import os
import sys
import shutil
import tempfile
import unittest
import subprocess

from nizam.transpiler import (
    Transpiler,
    ProjectBuilder,
    build_project,
    WasmLoaderGenerator,
)
from nizam.transpiler.cli import main as cli_main

# ── Phase 5 Tests ────────────────────────────────────────────────────────
class TestTranspilerPhase5(unittest.TestCase):
    """Phase 5: Full Standalone Native & WebAssembly (WASM) Deployment Test Suite."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="nizam_phase5_test_")
        self.workspace_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../..")
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_multi_module_project_discovery_and_transpile(self):
        """Test recursive Python source discovery and intermediate transpilation."""
        # Setup multi-file project
        app_py = os.path.join(self.test_dir, "app.py")
        utils_dir = os.path.join(self.test_dir, "utils")
        os.makedirs(utils_dir, exist_ok=True)
        helper_py = os.path.join(utils_dir, "helper.py")

        with open(helper_py, "w") as f:
            f.write(
                "def compute_cube(x: int) -> int:\n"
                "    return x * x * x\n"
            )

        with open(app_py, "w") as f:
            f.write(
                "def main() -> int:\n"
                "    val: int = 4\n"
                "    return val * 2\n"
            )

        builder = ProjectBuilder(
            source_path=self.test_dir,
            workspace_root=self.workspace_root,
            build_dir=os.path.join(self.test_dir, "build"),
        )
        sources = builder.discover_source_files()
        self.assertEqual(len(sources), 2)
        self.assertIn(app_py, sources)
        self.assertIn(helper_py, sources)

        entry = builder.determine_entrypoint(sources)
        self.assertEqual(entry, app_py)

        transpiled_map = builder.transpile_all(sources)
        self.assertEqual(len(transpiled_map), 2)
        for src, out_nz in transpiled_map.items():
            self.assertTrue(os.path.exists(out_nz), f"Transpiled file missing: {out_nz}")
            with open(out_nz, "r") as f:
                content = f.read()
                self.assertIn("fn ", content)

    def test_native_project_compilation_and_execution(self):
        """Test building and executing a standalone native binary."""
        main_py = os.path.join(self.test_dir, "main.py")
        out_bin = os.path.join(self.test_dir, "dist", "app_native")

        with open(main_py, "w") as f:
            f.write(
                "def main():\n"
                "    print('Native Execution Succeeded')\n"
            )

        result = build_project(
            source_path=main_py,
            output_path=out_bin,
            target="native",
            workspace_root=self.workspace_root,
        )

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(out_bin))
        self.assertGreater(result["binary_size"], 0)

        # Execute compiled native binary
        proc = subprocess.run([out_bin], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Native Execution Succeeded", proc.stdout)

    def test_release_stripping(self):
        """Test release mode symbol stripping on native executable."""
        main_py = os.path.join(self.test_dir, "main_rel.py")
        out_bin = os.path.join(self.test_dir, "dist", "app_rel")

        with open(main_py, "w") as f:
            f.write(
                "def main():\n"
                "    print('Release Stripped App Running')\n"
            )

        result = build_project(
            source_path=main_py,
            output_path=out_bin,
            target="native",
            release=True,
            workspace_root=self.workspace_root,
        )

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(out_bin))

        # Confirm executable still runs cleanly after strip
        proc = subprocess.run([out_bin], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Release Stripped App Running", proc.stdout)

    def test_wasm_compilation_and_wasi_execution(self):
        """Test building and executing a standalone WebAssembly (WASI) binary."""
        wasm_py = os.path.join(self.test_dir, "wasm_app.py")
        out_wasm = os.path.join(self.test_dir, "dist", "wasm_app.wasm")

        with open(wasm_py, "w") as f:
            f.write(
                "def main():\n"
                "    print('WebAssembly WASI Execution Succeeded')\n"
            )

        result = build_project(
            source_path=wasm_py,
            output_path=out_wasm,
            target="wasm32-wasi",
            web_loader=True,
            workspace_root=self.workspace_root,
        )

        self.assertTrue(result["success"])
        self.assertTrue(os.path.exists(out_wasm))
        self.assertGreater(result["binary_size"], 0)
        self.assertIsNotNone(result["loader_files"])

        # Execute using the canonical nizam_wasi.js runner
        nizam_wasi = os.path.join(self.workspace_root, "nizam_wasi.js")
        if os.path.exists(nizam_wasi) and shutil.which("node"):
            proc = subprocess.run(
                ["node", nizam_wasi, out_wasm],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("WebAssembly WASI Execution Succeeded", proc.stdout)

    def test_wasm_loader_generator(self):
        """Test standalone synthesis of index.html and nizam_app.js."""
        dist_dir = os.path.join(self.test_dir, "web_dist")
        generator = WasmLoaderGenerator(output_dir=dist_dir, app_title="PyThra Nizam Demo")
        files = generator.generate(wasm_filename="demo.wasm")

        html_path = files["html"]
        js_path = files["js"]

        self.assertTrue(os.path.exists(html_path))
        self.assertTrue(os.path.exists(js_path))

        with open(html_path, "r") as f:
            html_content = f.read()
            self.assertIn("PyThra Nizam Demo", html_content)
            self.assertIn('<div id="app-root">', html_content)
            self.assertIn('<script src="nizam_app.js">', html_content)
            self.assertIn("demo.wasm", html_content)

        with open(js_path, "r") as f:
            js_content = f.read()
            self.assertIn("wasi_snapshot_preview1", js_content)
            self.assertIn("__nizam_apply_patches", js_content)
            self.assertIn("NizamWasiRunner", js_content)

    def test_native_webview_shell_bindings(self):
        """Test native webview headers and Nizam bindings."""
        header_file = os.path.join(self.workspace_root, "mantiq", "src", "ui", "native_webview.h")
        c_file = os.path.join(self.workspace_root, "mantiq", "src", "ui", "native_webview.c")
        nz_file = os.path.join(self.workspace_root, "mantiq", "src", "ui", "native_webview.nz")

        self.assertTrue(os.path.exists(header_file), f"Header missing: {header_file}")
        self.assertTrue(os.path.exists(c_file), f"C file missing: {c_file}")
        self.assertTrue(os.path.exists(nz_file), f"Nizam file missing: {nz_file}")

        with open(nz_file, "r") as f:
            content = f.read()
            self.assertIn("struct WebviewWindow:", content)
            self.assertIn("nizam_webview_create", content)
            self.assertIn("apply_patches", content)

    def test_cli_build_driver(self):
        """Test CLI --build invocation for native and wasm targets."""
        cli_src = os.path.join(self.test_dir, "cli_sample.py")
        with open(cli_src, "w") as f:
            f.write(
                "def main():\n"
                "    print('CLI Build Completed')\n"
            )

        out_bin = os.path.join(self.test_dir, "cli_dist", "cli_sample")
        ret = cli_main([
            "--build", cli_src,
            "-o", out_bin,
            "--target", "native",
            "--workspace", self.workspace_root,
        ])
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.exists(out_bin))

        proc = subprocess.run([out_bin], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("CLI Build Completed", proc.stdout)


if __name__ == "__main__":
    unittest.main()
