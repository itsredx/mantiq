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
class TestNizamTranspilerPhase1(unittest.TestCase):

    def setUp(self):
        self.transpiler = Transpiler()
        # Find stage3 mantiq compiler
        self.workspace_root = os.path.abspath(os.path.join(PYTHON_ROOT, "..", ".."))
        self.compiler_bin = os.path.join(self.workspace_root, "stage3", "mantiq")
        if not os.path.exists(self.compiler_bin):
            self.compiler_bin = os.path.join(self.workspace_root, "mantiq", "mantiq")

    # ── Test 1: Recursive Fibonacci ────────────────────────────────────
    def test_fibonacci(self):
        py_code = """def fib(n: int) -> int:
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

if __name__ == '__main__':
    print(fib(10))
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("fn fib(n as i64) as i64:", nz_code)
        self.assertIn("if n <= 1:", nz_code)
        self.assertIn("return n", nz_code)
        self.assertIn("fn main() as i32:", nz_code)
        self.assertIn("printf(", nz_code)

    # ── Test 2: While Loops, Range Loops & Factorial ───────────────────
    def test_loops_and_arithmetic(self):
        py_code = """def factorial(n: int) -> int:
    res: int = 1
    i: int = 1
    while i <= n:
        res *= i
        i += 1
    return res

def sum_range(n: int) -> int:
    total: int = 0
    for i in range(n):
        total += i
    return total
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("fn factorial(n as i64) as i64:", nz_code)
        self.assertIn("while i <= n:", nz_code)
        self.assertIn("res *= i", nz_code)
        self.assertIn("fn sum_range(n as i64) as i64:", nz_code)
        self.assertIn("for i in 0..n:", nz_code)
        self.assertIn("total += i", nz_code)

    # ── Test 3: List Comprehensions ────────────────────────────────────
    def test_list_comprehensions(self):
        py_code = """def get_doubled(items: list[int]) -> list[int]:
    return [x * 2 for x in items if x > 0]
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("fn get_doubled(items as List[i64]) as List[i64]:", nz_code)
        self.assertIn("[for x in items: if x > 0: (x * 2)]", nz_code)

    # ── Test 4: If-Elif-Else Chains ────────────────────────────────────
    def test_if_elif_else(self):
        py_code = """def classify(score: int) -> int:
    if score >= 90:
        return 1
    elif score >= 75:
        return 2
    elif score >= 50:
        return 3
    else:
        return 4
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn("if score >= 90:", nz_code)
        self.assertIn("elif score >= 75:", nz_code)
        self.assertIn("elif score >= 50:", nz_code)
        self.assertIn("else:", nz_code)

    # ── Test 5: f-string Lowering ──────────────────────────────────────
    def test_fstrings(self):
        py_code = """def greet(name: str, count: int) -> str:
    msg: str = f"User {name} has {count} points"
    return msg
"""
        nz_code = self.transpiler.transpile(py_code)
        self.assertIn('var msg as String = "User " + name.to_string() + " has " + count.to_string() + " points"', nz_code)

    # ── Test 6: Differential Execution with Stage 3 Compiler ───────────
    def test_differential_execution_fibonacci(self):
        if not os.path.exists(self.compiler_bin):
            self.skipTest(f"Compiler binary not found at {self.compiler_bin}")

        py_code = """def fib(n: int) -> int:
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

if __name__ == '__main__':
    print(fib(10))
"""
        # 1. Run via Python 3
        py_proc = subprocess.run([sys.executable, "-c", py_code], capture_output=True, text=True)
        self.assertEqual(py_proc.returncode, 0)
        expected_output = py_proc.stdout.strip()
        self.assertEqual(expected_output, "55")

        # 2. Transpile to Nizam
        nz_code = self.transpiler.transpile(py_code)

        # 3. Write to temporary .nz file and run via mantiq run
        with tempfile.NamedTemporaryFile(suffix=".nz", mode="w", delete=False) as tf:
            tf.write(nz_code)
            temp_path = tf.name

        try:
            nz_proc = subprocess.run([self.compiler_bin, "run", temp_path], capture_output=True, text=True)
            self.assertEqual(nz_proc.returncode, 0, f"Nizam compiler error:\n{nz_proc.stderr}\nSTDOUT:\n{nz_proc.stdout}")
            lines = [l for l in nz_proc.stdout.strip().split("\n") if not l.startswith("zig: warning:")]
            actual_output = "\n".join(lines).strip()
            self.assertEqual(actual_output, expected_output, f"Output mismatch: expected '{expected_output}', got '{actual_output}'")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # ── Test 7: Differential Execution of Loops and Factorial ──────────
    def test_differential_execution_loops(self):
        if not os.path.exists(self.compiler_bin):
            self.skipTest(f"Compiler binary not found at {self.compiler_bin}")

        py_code = """def factorial(n: int) -> int:
    res: int = 1
    i: int = 1
    while i <= n:
        res *= i
        i += 1
    return res

if __name__ == '__main__':
    print(factorial(6))
"""
        # 1. Run via Python 3
        py_proc = subprocess.run([sys.executable, "-c", py_code], capture_output=True, text=True)
        self.assertEqual(py_proc.returncode, 0)
        expected_output = py_proc.stdout.strip()
        self.assertEqual(expected_output, "720")

        # 2. Transpile and execute via mantiq run
        nz_code = self.transpiler.transpile(py_code)
        with tempfile.NamedTemporaryFile(suffix=".nz", mode="w", delete=False) as tf:
            tf.write(nz_code)
            temp_path = tf.name

        try:
            nz_proc = subprocess.run([self.compiler_bin, "run", temp_path], capture_output=True, text=True, cwd=self.workspace_root)
            self.assertEqual(nz_proc.returncode, 0, f"Nizam compiler error:\n{nz_proc.stderr}\nSTDOUT:\n{nz_proc.stdout}")
            lines = [l for l in nz_proc.stdout.strip().split("\n") if not l.startswith("zig: warning:")]
            actual_output = "\n".join(lines).strip()
            self.assertEqual(actual_output, expected_output)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # ── Test 8: CLI Driver Invocation ──────────────────────────────────
    def test_cli_invocation(self):
        from nizam.transpiler.cli import main as cli_main
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tf_in:
            tf_in.write("def square(x: int) -> int:\n    return x * x\n")
            in_path = tf_in.name

        out_path = in_path.replace(".py", ".nz")
        try:
            ret = cli_main([in_path, "-o", out_path])
            self.assertEqual(ret, 0)
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("fn square(x as i64) as i64:", content)
            self.assertIn("return (x * x)", content)
        finally:
            if os.path.exists(in_path):
                os.remove(in_path)
            if os.path.exists(out_path):
                os.remove(out_path)

if __name__ == "__main__":
    unittest.main()
