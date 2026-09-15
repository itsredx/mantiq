# ── Imports ─────────────────────────────────────────────────────────────
import os
import sys
import shutil
import tempfile
import unittest

from nizam.transpiler import Transpiler, transpile
from nizam.transpiler.project import ProjectTranspiler

# ── Advanced Mantiq Transpiler Test Suite ───────────────────────────────
class TestMantiqTranspilerAdvanced(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="mantiq_adv_test_")
        self.src_dir = os.path.join(self.temp_dir, "src_project")
        self.out_dir = os.path.join(self.temp_dir, "out_project")
        os.makedirs(self.src_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ── Test 1: Native Mantiq Class & Super Delegation ─────────────────
    def test_mantiq_class_syntax_and_super(self):
        py_code = """
class BaseWidget:
    def __init__(self, title: str):
        self.title = title

    def render(self) -> str:
        return self.title

class CustomButton(BaseWidget):
    def __init__(self, title: str, count: int):
        super().__init__(title)
        self.count = count

    def render(self) -> str:
        return super().render()
"""
        transpiler = Transpiler(syntax="mq")
        mq_code = transpiler.transpile(py_code)

        self.assertIn("class BaseWidget:", mq_code)
        self.assertIn("public var title as String", mq_code)
        self.assertIn("class CustomButton(BaseWidget):", mq_code)
        self.assertIn("public var count as i64", mq_code)
        self.assertIn("super().render()", mq_code)

    # ── Test 2: Multiple Inheritance & Icons Merging ───────────────────
    def test_icons_multiple_inheritance_merging(self):
        py_code = """
class IconsSharp:
    home_sharp: str = "home_sharp_icon"

class IconsRounded:
    home_rounded: str = "home_rounded_icon"

class Icons(IconsSharp, IconsRounded):
    pass
"""
        transpiler = Transpiler(syntax="mq")
        mq_code = transpiler.transpile(py_code)

        self.assertIn("class Icons:", mq_code)
        self.assertIn('public var home_sharp as String = "home_sharp_icon" to cstr', mq_code)
        self.assertIn('public var home_rounded as String = "home_rounded_icon" to cstr', mq_code)

    # ── Test 3: Wildcard Import Expansion ──────────────────────────────
    def test_wildcard_import_expansion(self):
        project_index = {
            "base": {"symbols": ["IconData", "BASE_VERSION"]},
            ".base": {"symbols": ["IconData", "BASE_VERSION"]},
        }
        py_code = """
from .base import *

class MyIcon:
    def __init__(self, data: IconData):
        self.data = data
"""
        transpiler = Transpiler(syntax="mq", project_index=project_index)
        mq_code = transpiler.transpile(py_code)

        self.assertNotIn("import *", mq_code)
        self.assertIn("from .base import IconData, BASE_VERSION", mq_code)

    # ── Test 4: String Methods Transpilation ───────────────────────────
    def test_string_methods_transpilation(self):
        py_code = """
def test_strings(s: str) -> bool:
    a = s.startswith("abc")
    b = s.endswith("xyz")
    c = s.lower()
    d = s.upper()
    e = s.strip()
    f = s.replace("foo", "bar")
    g = s.split(",")
    return a and b
"""
        transpiler = Transpiler(syntax="mq")
        mq_code = transpiler.transpile(py_code)

        self.assertIn('s.startswith("abc" to cstr)', mq_code)
        self.assertIn('s.endswith("xyz" to cstr)', mq_code)
        self.assertIn("s.lower()", mq_code)
        self.assertIn("s.upper()", mq_code)
        self.assertIn("s.strip()", mq_code)
        self.assertIn('s.replace("foo" to cstr, "bar" to cstr)', mq_code)
        self.assertIn('s.split("," to cstr)', mq_code)

    # ── Test 5: Dict Items Iteration Lowering ───────────────────────────
    def test_dict_items_lowering(self):
        py_code = """
def iterate_map(d: dict):
    for k, v in d.items():
        print(k, v)
"""
        transpiler = Transpiler(syntax="mq")
        mq_code = transpiler.transpile(py_code)

        self.assertIn("for k in d.keys():", mq_code)
        self.assertIn("let v = d[k]", mq_code)
        self.assertNotIn("d.items()", mq_code)

    # ── Test 6: Dict Get and Pop Lowering ───────────────────────────────
    def test_dict_get_and_pop_lowering(self):
        py_code = """
def check_dict(d: dict):
    val = d.get("key", 100)
    removed = d.pop("key")
"""
        transpiler = Transpiler(syntax="mq")
        mq_code = transpiler.transpile(py_code)

        self.assertIn('(d["key" to cstr] if d.has("key" to cstr) else 100)', mq_code)
        self.assertIn('d.remove("key" to cstr)', mq_code)

    # ── Test 7: Project Transpiler Mantiq Mode and Compiler Check ──────
    def test_project_transpiler_mantiq_mode_and_compiler_check(self):
        # 1. base.py
        with open(os.path.join(self.src_dir, "base.py"), "w") as f:
            f.write("class BaseItem:\n    val: int = 42\n")

        # 2. icons.py importing from base
        with open(os.path.join(self.src_dir, "icons.py"), "w") as f:
            f.write("from .base import *\nclass IconWidget(BaseItem):\n    active: bool = True\n")

        # 3. app.py
        with open(os.path.join(self.src_dir, "app.py"), "w") as f:
            f.write("from .icons import IconWidget\ndef start() -> int:\n    w = IconWidget()\n    return 0\n")

        proj_transpiler = ProjectTranspiler(
            source_dir=self.src_dir,
            output_dir=self.out_dir,
            syntax="mq",
            check=True,
        )
        manifest = proj_transpiler.execute()

        self.assertEqual(manifest["summary"]["transpiled_success"], 3)
        self.assertEqual(manifest["summary"]["transpiled_fallback"], 0)
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, "base.mq")))
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, "icons.mq")))
        self.assertTrue(os.path.isfile(os.path.join(self.out_dir, "app.mq")))

        # Check compiler verification passed for all generated files
        self.assertEqual(len(manifest["check_results"]["failed"]), 0)
        self.assertGreaterEqual(len(manifest["check_results"]["passed"]), 3)

if __name__ == "__main__":
    unittest.main()
