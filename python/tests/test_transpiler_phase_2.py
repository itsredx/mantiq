# ── Imports ────────────────────────────────────────────────────────────
import unittest
import os
import sys
import tempfile
import subprocess

# Add python directory to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_ROOT = os.path.dirname(CURRENT_DIR)
if PYTHON_ROOT not in sys.path:
    sys.path.insert(0, PYTHON_ROOT)

from nizam.transpiler import Transpiler, transpile

# ── Test Suite ─────────────────────────────────────────────────────────
class TestNizamTranspilerPhase2(unittest.TestCase):

    def setUp(self):
        self.transpiler = Transpiler()
        # Find stage3 mantiq compiler
        self.workspace_root = os.path.abspath(os.path.join(PYTHON_ROOT, "..", ".."))
        self.compiler_bin = os.path.join(self.workspace_root, "stage3", "mantiq")
        if not os.path.exists(self.compiler_bin):
            self.compiler_bin = os.path.join(self.workspace_root, "mantiq", "mantiq")

    # ── Test 1: Class to Struct Lowering & Field Inference ─────────────
    def test_class_to_struct_lowering(self):
        py_code = """class Point:
    x: int
    y: int

    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    def sum(self) -> int:
        return self.x + self.y
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("struct Point:", nz_code)
        self.assertIn("public var x as i64", nz_code)
        self.assertIn("public var y as i64", nz_code)
        self.assertIn("public fn init(", nz_code)
        self.assertIn("public fn sum(self as ptr[Point]) as i64:", nz_code)
        self.assertIn("(deref self).x + (deref self).y", nz_code)

    # ── Test 2: Receiver Method Field Mutation ─────────────────────────
    def test_receiver_method_mutation(self):
        py_code = """class Counter:
    def __init__(self, start: int = 0):
        self.count = start

    def increment(self, step: int) -> None:
        self.count += step

    def get(self) -> int:
        return self.count
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("struct Counter:", nz_code)
        self.assertIn("public var count as i64", nz_code)
        self.assertIn("public fn increment(self as ptr[Counter], step as i64):", nz_code)
        self.assertIn("(deref self).count += step", nz_code)
        self.assertIn("public fn get(self as ptr[Counter]) as i64:", nz_code)
        self.assertIn("return (deref self).count", nz_code)

    # ── Test 3: PyThra Declarative Widget (StatelessWidget) ────────────
    def test_pythra_stateless_widget(self):
        py_code = """class CustomButton(StatelessWidget):
    def __init__(self, label: str, count: int):
        super().__init__()
        self.label = label
        self.count = count

    def get_count(self) -> int:
        return self.count
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("struct CustomButton:", nz_code)
        self.assertIn("public var label as String", nz_code)
        self.assertIn("public var count as i64", nz_code)
        self.assertIn("// super().__init__()", nz_code)
        self.assertIn("public fn get_count(self as ptr[CustomButton]) as i64:", nz_code)

    # ── Test 4: PyThra State Lifecycle and set_state Lowering ──────────
    def test_pythra_state_lifecycle(self):
        py_code = """class CounterState(State):
    def __init__(self):
        self.count = 0

    def inc(self) -> None:
        self.set_state(lambda: self._inc_helper())

    def _inc_helper(self) -> None:
        self.count += 1
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("struct CounterState:", nz_code)
        self.assertIn("public var count as i64", nz_code)
        self.assertIn("public fn inc(self as ptr[CounterState]):", nz_code)
        self.assertIn("/* nizam_ui_mark_dirty(self) */", nz_code)
        self.assertIn("fn _inc_helper(self as ptr[CounterState]):", nz_code)
        self.assertIn("(deref self).count += 1", nz_code)

    # ── Test 5: Keyword Arguments in Constructor Call ──────────────────
    def test_constructor_kwargs(self):
        py_code = """class Config:
    def __init__(self, width: int, height: int, debug: bool):
        self.width = width
        self.height = height
        self.debug = debug

cfg = Config(width=800, height=600, debug=True)
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("struct Config:", nz_code)
        self.assertIn("Config.init(width = 800, height = 600, debug = True)", nz_code)

    # ── Test 6: Differential Execution - Counter Struct & Mutation ─────
    def test_differential_execution_counter(self):
        if not os.path.exists(self.compiler_bin):
            self.skipTest(f"Compiler binary not found at {self.compiler_bin}")

        py_code = """class Counter:
    def __init__(self, start: int):
        self.count = start

    def increment(self, step: int) -> None:
        self.count += step

    def get_count(self) -> int:
        return self.count

if __name__ == '__main__':
    c = Counter(10)
    c.increment(5)
    c.increment(2)
    print(c.get_count())
"""
        # 1. Run in Python
        py_proc = subprocess.run([sys.executable, "-c", py_code], capture_output=True, text=True)
        self.assertEqual(py_proc.returncode, 0, f"Python error:\n{py_proc.stderr}")
        expected_output = py_proc.stdout.strip()
        self.assertEqual(expected_output, "17")

        # 2. Transpile to Nizam
        nz_code = self.transpiler.transpile(py_code)

        # 3. Execute via Stage 3 Mantiq compiler
        with tempfile.NamedTemporaryFile(suffix=".nz", mode="w", delete=False) as tf:
            tf.write(nz_code)
            temp_path = tf.name

        try:
            nz_proc = subprocess.run([self.compiler_bin, "run", temp_path, "--lib-dir", "mantiq"], capture_output=True, text=True, cwd=self.workspace_root)
            self.assertEqual(nz_proc.returncode, 0, f"Nizam compiler error:\n{nz_proc.stderr}\nSTDOUT:\n{nz_proc.stdout}\nNZ CODE:\n{nz_code}")
            lines = [l for l in nz_proc.stdout.strip().split("\n") if not l.startswith("zig: warning:")]
            actual_output = "\n".join(lines).strip()
            self.assertEqual(actual_output, expected_output, f"Output mismatch: expected '{expected_output}', got '{actual_output}'")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # ── Test 7: Differential Execution - Multi-Method Point Operations ─
    def test_differential_execution_point(self):
        if not os.path.exists(self.compiler_bin):
            self.skipTest(f"Compiler binary not found at {self.compiler_bin}")

        py_code = """class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    def sum(self) -> int:
        return self.x + self.y

    def scale(self, factor: int) -> None:
        self.x = self.x * factor
        self.y = self.y * factor

if __name__ == '__main__':
    p = Point(3, 4)
    print(p.sum())
    p.scale(10)
    print(p.sum())
"""
        # 1. Run in Python
        py_proc = subprocess.run([sys.executable, "-c", py_code], capture_output=True, text=True)
        self.assertEqual(py_proc.returncode, 0, f"Python error:\n{py_proc.stderr}")
        expected_output = py_proc.stdout.strip()
        self.assertEqual(expected_output, "7\n70")

        # 2. Transpile to Nizam
        nz_code = self.transpiler.transpile(py_code)

        # 3. Execute via Stage 3 Mantiq compiler
        with tempfile.NamedTemporaryFile(suffix=".nz", mode="w", delete=False) as tf:
            tf.write(nz_code)
            temp_path = tf.name

        try:
            nz_proc = subprocess.run([self.compiler_bin, "run", temp_path, "--lib-dir", "mantiq"], capture_output=True, text=True, cwd=self.workspace_root)
            self.assertEqual(nz_proc.returncode, 0, f"Nizam compiler error:\n{nz_proc.stderr}\nSTDOUT:\n{nz_proc.stdout}\nNZ CODE:\n{nz_code}")
            lines = [l for l in nz_proc.stdout.strip().split("\n") if not l.startswith("zig: warning:")]
            actual_output = "\n".join(lines).strip()
            self.assertEqual(actual_output, expected_output, f"Output mismatch: expected '{expected_output}', got '{actual_output}'")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # ── Test 8: Method Calling Method on Self ──────────────────────────
    def test_method_delegation_on_self(self):
        py_code = """class MathEngine:
    def __init__(self, base: int):
        self.base = base

    def plus(self, n: int) -> int:
        return self.base + n

    def plus_twice(self, n: int) -> int:
        first = self.plus(n)
        return first + n

if __name__ == '__main__':
    engine = MathEngine(10)
    print(engine.plus_twice(5))
"""
        py_proc = subprocess.run([sys.executable, "-c", py_code], capture_output=True, text=True)
        self.assertEqual(py_proc.returncode, 0)
        expected_output = py_proc.stdout.strip()
        self.assertEqual(expected_output, "20")

        nz_code = self.transpiler.transpile(py_code)
        with tempfile.NamedTemporaryFile(suffix=".nz", mode="w", delete=False) as tf:
            tf.write(nz_code)
            temp_path = tf.name

        try:
            nz_proc = subprocess.run([self.compiler_bin, "run", temp_path, "--lib-dir", "mantiq"], capture_output=True, text=True, cwd=self.workspace_root)
            self.assertEqual(nz_proc.returncode, 0, f"Nizam compiler error:\n{nz_proc.stderr}\nSTDOUT:\n{nz_proc.stdout}\nNZ CODE:\n{nz_code}")
            lines = [l for l in nz_proc.stdout.strip().split("\n") if not l.startswith("zig: warning:")]
            actual_output = "\n".join(lines).strip()
            self.assertEqual(actual_output, expected_output)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # ── Test 9: Multiple Classes in One Module ─────────────────────────
    def test_multiple_classes(self):
        py_code = """class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

class Rectangle:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height

    def area(self) -> int:
        return self.width * self.height

if __name__ == '__main__':
    p = Point(1, 2)
    r = Rectangle(10, 20)
    print(r.area())
"""
        py_proc = subprocess.run([sys.executable, "-c", py_code], capture_output=True, text=True)
        self.assertEqual(py_proc.returncode, 0)
        expected_output = py_proc.stdout.strip()
        self.assertEqual(expected_output, "200")

        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("struct Point:", nz_code)
        self.assertIn("struct Rectangle:", nz_code)

        with tempfile.NamedTemporaryFile(suffix=".nz", mode="w", delete=False) as tf:
            tf.write(nz_code)
            temp_path = tf.name

        try:
            nz_proc = subprocess.run([self.compiler_bin, "run", temp_path, "--lib-dir", "mantiq"], capture_output=True, text=True, cwd=self.workspace_root)
            self.assertEqual(nz_proc.returncode, 0, f"Nizam compiler error:\n{nz_proc.stderr}\nSTDOUT:\n{nz_proc.stdout}\nNZ CODE:\n{nz_code}")
            lines = [l for l in nz_proc.stdout.strip().split("\n") if not l.startswith("zig: warning:")]
            actual_output = "\n".join(lines).strip()
            self.assertEqual(actual_output, expected_output)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
