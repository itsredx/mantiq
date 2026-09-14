# ── Imports ─────────────────────────────────────────────────────────────
import os
import sys
import json
import unittest
import tempfile
import subprocess
import concurrent.futures

# Add python directory to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_ROOT = os.path.dirname(CURRENT_DIR)
if PYTHON_ROOT not in sys.path:
    sys.path.insert(0, PYTHON_ROOT)

from nizam.reconciler import (
    WidgetNode,
    reconcile,
    reconcile_json,
    compile_reconciler_extension,
    get_native_reconciler,
    is_native_available,
    PythonReconciler,
)

# ── Test Suite ───────────────────────────────────────────────────────────
class TestNizamTranspilerPhase3(unittest.TestCase):

    def setUp(self):
        self.workspace_root = os.path.abspath(os.path.join(PYTHON_ROOT, "..", ".."))
        self.compiler_bin = os.path.join(self.workspace_root, "stage3", "mantiq")
        if not os.path.exists(self.compiler_bin):
            self.compiler_bin = os.path.join(self.workspace_root, "mantiq", "mantiq")
        self.reconciler_src = os.path.join(self.workspace_root, "mantiq", "src", "ui", "reconciler.nz")

    def assertPatchesEqual(self, patches1, patches2):
        self.assertEqual(len(patches1), len(patches2), f"Different patch lengths: {patches1} vs {patches2}")
        for p1, p2 in zip(patches1, patches2):
            self.assertEqual(p1["action"], p2["action"])
            self.assertEqual(p1["html_id"], p2["html_id"])
            if p1["action"] == "UPDATE":
                kvs1 = set(p1["payload"].split(";")) if p1["payload"] else set()
                kvs2 = set(p2["payload"].split(";")) if p2["payload"] else set()
                self.assertEqual(kvs1, kvs2)
            else:
                self.assertEqual(p1["payload"], p2["payload"])

    # ── Test 1: Native Reconciler Standalone Execution ───────────────────
    def test_native_reconciler_standalone_execution(self):
        """Verify reconciler.nz compiles and executes standalone via mantiq run."""
        self.assertTrue(os.path.isfile(self.reconciler_src), f"Missing source: {self.reconciler_src}")
        self.assertTrue(os.path.isfile(self.compiler_bin), f"Missing compiler: {self.compiler_bin}")

        cmd = [self.compiler_bin, "run", self.reconciler_src, "--lib-dir", os.path.join(self.workspace_root, "mantiq")]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Standalone run failed:\n{res.stderr}\n{res.stdout}")
        self.assertIn("=== Nizam UI Reconciler Standalone Test ===", res.stdout)
        self.assertIn("Reconciliation result:", res.stdout)
        self.assertIn("✔ All Nizam UI Reconciler verification tests passed!", res.stdout)

    # ── Test 2: C-Extension Compilation ──────────────────────────────────
    def test_compile_reconciler_c_extension(self):
        """Verify building the reconciler as a PEP 384 ABI3 shared library."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_so = os.path.join(tmp_dir, "nizam_reconciler.abi3.so")
            built_path = compile_reconciler_extension(output_path=out_so)
            self.assertEqual(built_path, out_so)
            self.assertTrue(os.path.isfile(out_so))
            self.assertGreater(os.path.getsize(out_so), 1024)

    # ── Test 3: C-Extension Dynamic Import & Symbol Surface ──────────────
    def test_c_extension_import_and_symbols(self):
        """Verify dynamic loading and symbol presence of the native reconciler."""
        self.assertTrue(is_native_available(), "Native reconciler extension could not be loaded")
        native_mod = get_native_reconciler()
        self.assertIsNotNone(native_mod)
        self.assertTrue(hasattr(native_mod, "reconcile_json"))
        self.assertTrue(hasattr(native_mod, "patches_to_json"))

    # ── Test 4: Differential Correctness: Property Updates ───────────────
    def test_diff_prop_updates(self):
        """Verify property updates produce identical patch semantics in native and pure Python."""
        old = WidgetNode("div", id="root", props={"theme": "dark", "lang": "en"}, children=[
            WidgetNode("span", id="s1", key="k1", props={"text": "hello", "color": "red"}),
            WidgetNode("span", id="s2", key="k2", props={"text": "fixed"}),
        ])
        new = WidgetNode("div", id="root", props={"theme": "light", "lang": "en"}, children=[
            WidgetNode("span", id="s1", key="k1", props={"text": "world", "color": "blue"}),
            WidgetNode("span", id="s2", key="k2", props={"text": "fixed"}),
        ])

        patches_native = reconcile(old, new, use_native=True)
        patches_py = reconcile(old, new, use_native=False)

        self.assertPatchesEqual(patches_native, patches_py)
        # Should have root UPDATE (theme=light) and s1 UPDATE (text=world;color=blue)
        actions = [p["action"] for p in patches_native]
        self.assertEqual(actions, ["UPDATE", "UPDATE"])
        self.assertEqual(patches_native[0]["html_id"], "root")
        self.assertIn("theme=light", patches_native[0]["payload"])
        self.assertEqual(patches_native[1]["html_id"], "s1")

    # ── Test 5: Differential Correctness: Node Insertion & Removal ───────
    def test_diff_insertion_and_removal(self):
        """Verify child node insertions and removals match between engines."""
        old = WidgetNode("div", id="root", props={}, children=[
            WidgetNode("p", id="p1", key="k1", props={"content": "para 1"}),
            WidgetNode("p", id="p2", key="k2", props={"content": "para 2"}),
        ])
        new = WidgetNode("div", id="root", props={}, children=[
            WidgetNode("p", id="p1", key="k1", props={"content": "para 1"}),
            WidgetNode("p", id="p3", key="k3", props={"content": "para 3"}),
        ])

        patches_native = reconcile(old, new, use_native=True)
        patches_py = reconcile(old, new, use_native=False)

        self.assertEqual(patches_native, patches_py)
        actions = [p["action"] for p in patches_native]
        self.assertIn("REMOVE", actions)
        self.assertIn("INSERT", actions)

    # ── Test 6: Differential Correctness: Node Replacement ───────────────
    def test_diff_tag_replacement(self):
        """Verify tag changes trigger REPLACE patches with new HTML stubs."""
        old = WidgetNode("div", id="root", props={}, children=[
            WidgetNode("input", id="inp1", key="k1", props={"type": "text"}),
        ])
        new = WidgetNode("div", id="root", props={}, children=[
            WidgetNode("textarea", id="inp1", key="k1", props={"rows": "4"}),
        ])

        patches_native = reconcile(old, new, use_native=True)
        patches_py = reconcile(old, new, use_native=False)

        self.assertEqual(patches_native, patches_py)
        self.assertEqual(len(patches_native), 1)
        self.assertEqual(patches_native[0]["action"], "REPLACE")
        self.assertIn("data-type=\"textarea\"", patches_native[0]["payload"])

    # ── Test 7: Differential Correctness: Keyed Child Reordering (MOVE) ──
    def test_diff_keyed_child_move(self):
        """Verify O(N) keyed reordering detects out-of-sequence moves identically."""
        old = WidgetNode("ul", id="list", props={}, children=[
            WidgetNode("li", id="li_a", key="a", props={"title": "Item A"}),
            WidgetNode("li", id="li_b", key="b", props={"title": "Item B"}),
            WidgetNode("li", id="li_c", key="c", props={"title": "Item C"}),
        ])
        # Reversed list: C, B, A
        new = WidgetNode("ul", id="list", props={}, children=[
            WidgetNode("li", id="li_c", key="c", props={"title": "Item C"}),
            WidgetNode("li", id="li_b", key="b", props={"title": "Item B"}),
            WidgetNode("li", id="li_a", key="a", props={"title": "Item A"}),
        ])

        patches_native = reconcile(old, new, use_native=True)
        patches_py = reconcile(old, new, use_native=False)

        self.assertEqual(patches_native, patches_py)
        move_actions = [p for p in patches_native if p["action"] == "MOVE"]
        self.assertEqual(len(move_actions), 2)
        moved_ids = [p["html_id"] for p in move_actions]
        self.assertEqual(moved_ids, ["li_b", "li_a"])

    # ── Test 8: Zero-GIL Concurrency Across Multiple Threads ─────────────
    def test_zero_gil_multi_threaded_concurrency(self):
        """Verify @nogil functions safely run concurrently on multiple Python threads."""
        def reconcile_task(thread_id: int):
            old = WidgetNode("div", id=f"root_{thread_id}", props={"val": "old"}, children=[
                WidgetNode("span", id=f"node_{thread_id}_{i}", key=f"k_{i}", props={"num": str(i)})
                for i in range(25)
            ])
            new = WidgetNode("div", id=f"root_{thread_id}", props={"val": "new"}, children=[
                WidgetNode("span", id=f"node_{thread_id}_{i}", key=f"k_{i}", props={"num": str(i + 100)})
                for i in range(25)
            ])
            return len(reconcile(old, new, use_native=True))

        thread_count = 16
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(reconcile_task, range(thread_count)))

        self.assertEqual(len(results), thread_count)
        # Root update (+1) + 25 children update (+25) = 26 patches each
        self.assertTrue(all(r == 26 for r in results), f"Unexpected patch counts: {results}")

    # ── Test 9: Transpiler CLI --build-reconciler Integration ────────────
    def test_cli_build_reconciler_option(self):
        """Verify the CLI supports --build-reconciler to produce native extension."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_so = os.path.join(tmp_dir, "nizam_reconciler.abi3.so")
            cmd = [
                sys.executable,
                "-m",
                "nizam.transpiler",
                "--build-reconciler",
                "-o",
                out_so,
            ]
            env = os.environ.copy()
            env["PYTHONPATH"] = PYTHON_ROOT
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"CLI build failed:\n{res.stderr}\n{res.stdout}")
            self.assertTrue(os.path.isfile(out_so))
            self.assertIn("✔ Native reconciler compiled successfully:", res.stdout)

if __name__ == "__main__":
    unittest.main()
