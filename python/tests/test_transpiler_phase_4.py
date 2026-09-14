# ── Phase 4 Transpiler Test Suite: Foreign Dynamic Interop & extern[python] ─
import unittest
import os
import sys
import tempfile
import subprocess
from nizam.transpiler import transpile, transpile_file, Transpiler
from nizam.transpiler.foreign import DependencyClassifier, ForeignModuleRegistry, ForeignFunctionSignature
from nizam.transpiler.cli import main as cli_main

class TestTranspilerPhase4(unittest.TestCase):
    """Test suite verifying Phase 4 foreign Python FFI interop and stub generation."""

    def setUp(self):
        self.transpiler = Transpiler(foreign_mode="extern")

    # ── Test 1: Boundary & Dependency Classifier ───────────────────────
    def test_dependency_classifier(self):
        classifier = DependencyClassifier()
        # Standard library modules
        self.assertTrue(classifier.is_foreign("math"))
        self.assertTrue(classifier.is_foreign("os"))
        self.assertTrue(classifier.is_foreign("sys"))
        self.assertTrue(classifier.is_foreign("json"))
        self.assertTrue(classifier.is_foreign("time"))

        # Third-party libraries
        self.assertTrue(classifier.is_foreign("PySide6"))
        self.assertTrue(classifier.is_foreign("PySide6.QtWidgets"))
        self.assertTrue(classifier.is_foreign("numpy"))
        self.assertTrue(classifier.is_foreign("torch"))

        # Local workspace check
        workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        classifier_ws = DependencyClassifier(workspace_root=workspace_root)
        self.assertTrue(classifier_ws.is_local_transpilable("nizam.transpiler"))
        self.assertFalse(classifier_ws.is_foreign("nizam.transpiler"))

    # ── Test 2: Foreign Module Registry & Stub Generation ──────────────
    def test_foreign_module_registry(self):
        registry = ForeignModuleRegistry()
        registry.register_import("math")
        sig = registry.record_call("math", "sqrt", ["f64"])
        self.assertEqual(sig.name, "sqrt")
        self.assertEqual(sig.return_type, "f64")
        self.assertEqual(sig.params, [("x", "f64")])

        extern_lines = registry.generate_extern_blocks()
        extern_text = "\n".join(extern_lines)
        self.assertIn('extern[python] "math":', extern_text)
        self.assertIn("fn sqrt(x as f64) as f64", extern_text)

        # Dynamic / custom unknown function fallback
        sig2 = registry.record_call("custom_lib", "process", ["cstr", "i64"])
        self.assertEqual(sig2.return_type, "PyObject")
        self.assertEqual(sig2.params, [("arg0", "cstr"), ("arg1", "i64")])

    # ── Test 3: Standard Library extern[python] Lowering ────────────────
    def test_standard_library_math_lowering(self):
        code = """
import math

val = math.sqrt(144.0)
p = math.pow(2.0, 10.0)
"""
        nz = transpile(code, foreign_mode="extern")
        self.assertIn('extern[python] "math":', nz)
        self.assertIn("fn pow(base as f64, exp as f64) as f64", nz)
        self.assertIn("fn sqrt(x as f64) as f64", nz)
        self.assertIn("var val as f64 = sqrt(144.0)", nz)
        self.assertIn("var p as f64 = pow(2.0, 10.0)", nz)

    # ── Test 4: from ... import Foreign Lowering ───────────────────────
    def test_from_import_foreign_lowering(self):
        code = """
from math import sqrt, floor

s = sqrt(81.0)
fl = floor(3.7)
"""
        nz = transpile(code, foreign_mode="extern")
        self.assertIn('extern[python] "math":', nz)
        self.assertIn("fn floor(x as f64) as f64", nz)
        self.assertIn("fn sqrt(x as f64) as f64", nz)
        self.assertIn("var s as f64 = sqrt(81.0)", nz)
        self.assertIn("var fl as f64 = floor(3.7)", nz)

    # ── Test 5: os.path and cstr Parameter Lowering ────────────────────
    def test_os_path_join_lowering(self):
        code = """
import os.path

p = os.path.join("root", "dir")
"""
        nz = transpile(code, foreign_mode="extern")
        self.assertIn('extern[python] "os.path":', nz)
        self.assertIn("fn join(a as cstr, b as cstr) as cstr", nz)
        self.assertIn('var p as cstr = join("root" to cstr, "dir" to cstr)', nz)

    # ── Test 6: Desktop GUI Shell (PySide6 / PyQt) Integration ─────────
    def test_desktop_gui_shell_lowering(self):
        code = """
import sys
from PySide6.QtWidgets import QApplication, QMainWindow

app = QApplication(sys.argv)
win = QMainWindow()
"""
        nz = transpile(code, foreign_mode="extern")
        self.assertIn('extern[python] "PySide6.QtWidgets":', nz)
        self.assertIn("fn QApplication(arg0 as PyObject) as PyObject", nz)
        self.assertIn("fn QMainWindow() as PyObject", nz)
        self.assertIn("var app as PyObject = QApplication([])", nz)
        self.assertIn("var win as PyObject = QMainWindow()", nz)

    # ── Test 7: Dynamic Introspection (getattr, setattr, hasattr) ───────
    def test_dynamic_introspection(self):
        code = """
class Widget:
    title: str
    count: int

w = Widget()
setattr(w, "title", "Custom")
t = getattr(w, "title")
has_t = hasattr(w, "title")
"""
        nz = transpile(code)
        self.assertIn('w.title = "Custom" to cstr', nz)
        self.assertIn("var t as String = w.title", nz)
        self.assertIn('var has_t as bool = w.has("title" to cstr)', nz)

    # ── Test 8: CLI and Mode Switching (extern vs import) ──────────────
    def test_mode_switching(self):
        code = """
import math
v = math.sqrt(25.0)
"""
        # 1. Extern mode
        nz_extern = transpile(code, foreign_mode="extern")
        self.assertIn('extern[python] "math":', nz_extern)
        self.assertIn("var v as f64 = sqrt(25.0)", nz_extern)

        # 2. Dynamic import mode
        nz_import = transpile(code, foreign_mode="import")
        self.assertIn("import[python] math", nz_import)
        self.assertIn("var v as f64 = math.sqrt(25.0)", nz_import)

    # ── Test 9: Differential Execution with stage3/mantiq run ──────────
    def test_differential_native_execution(self):
        mantiq_bin = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../stage3/mantiq"))
        if not os.path.exists(mantiq_bin) or not os.access(mantiq_bin, os.X_OK):
            self.skipTest(f"stage3/mantiq binary not found at {mantiq_bin}")

        mantiq_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

        code = """
import math
import os.path

s = math.sqrt(144.0)
p = os.path.join("usr", "local")
print("Native Sqrt:", s)
print("Native Join:", p)
"""
        nz_code = transpile(code, foreign_mode="extern")
        with tempfile.NamedTemporaryFile(suffix=".nz", mode="w", delete=False) as f:
            f.write(nz_code)
            tmp_path = f.name

        try:
            res = subprocess.run(
                [mantiq_bin, "run", tmp_path, "--lib-dir", mantiq_dir],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(res.returncode, 0, f"mantiq run failed: {res.stderr}")
            self.assertIn("Native Sqrt: 12.000000", res.stdout)
            self.assertIn("Native Join: usr/local", res.stdout)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
