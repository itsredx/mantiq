# ── Imports ─────────────────────────────────────────────────────────────
import os
import sys
import shutil
import json
import fnmatch
import subprocess
import ast
from typing import List, Dict, Set, Optional, Any, Tuple
from . import Transpiler
from .types import TypeEnvironment
from .classes import ClassTransformer
from .foreign import DependencyClassifier

# ── Project Directory Transpiler ────────────────────────────────────────
class ProjectTranspiler:
    """Recursively scans and transpiles a Python project directory into a parallel
    Nizam (.nz) or Mantiq (.mq) project structure, replicating assets, detecting
    Cython (.so/.pyx) extensions, and validating generated code via check mode.
    """

    DEFAULT_IGNORE_PATTERNS: List[str] = [
        ".git",
        ".svn",
        ".hg",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        "*.egg-info",
        "build",
        "dist",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        ".tox",
        ".idea",
        ".vscode",
        ".DS_Store",
    ]

    def __init__(
        self,
        source_dir: str,
        output_dir: str,
        syntax: str = "nz",
        check: bool = False,
        copy_assets: bool = True,
        copy_extensions: bool = True,
        bridge_cython: bool = True,
        ignore_patterns: Optional[List[str]] = None,
        foreign_mode: str = "extern",
        workspace_root: Optional[str] = None,
        mantiq_bin: Optional[str] = None,
    ):
        self.source_dir = os.path.abspath(source_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.syntax = "mq" if syntax.lower() in ("mq", "mantiq") else "nz"
        self.target_ext = f".{self.syntax}"
        self.check = check
        self.copy_assets = copy_assets
        self.copy_extensions = copy_extensions
        self.bridge_cython = bridge_cython
        self.ignore_patterns = self.DEFAULT_IGNORE_PATTERNS + (ignore_patterns or [])
        self.foreign_mode = foreign_mode
        self.workspace_root = os.path.abspath(workspace_root) if workspace_root else self.source_dir
        self.mantiq_bin = mantiq_bin or self._locate_mantiq_binary()

        self.scanned_py: List[str] = []
        self.scanned_cython: List[str] = []
        self.scanned_assets: List[str] = []
        self.scanned_ignored: List[str] = []

        self.transpiled_files: Dict[str, str] = {}
        self.transpile_errors: List[Dict[str, Any]] = []
        self.copied_assets: List[str] = []
        self.copied_extensions: List[str] = []
        self.bridged_extensions: List[Dict[str, Any]] = []
        self.check_results: Dict[str, Any] = {"passed": [], "failed": []}
        self.project_index: Dict[str, Any] = {}
        self.class_index: Dict[str, Any] = {}

    def _locate_mantiq_binary(self) -> Optional[str]:
        candidates = [
            os.path.join(self.workspace_root, "stage3", "mantiq"),
            os.path.join(self.workspace_root, "mantiq", "nizam"),
            os.path.join(self.workspace_root, "stage3", "nizam"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../stage3/mantiq")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../stage3/mantiq")),
            os.path.expanduser("~/.local/bin/mantiq"),
            os.path.expanduser("~/.local/bin/nizam"),
            "/usr/local/bin/mantiq",
            "/usr/local/bin/nizam",
        ]
        for cand in candidates:
            if os.path.exists(cand) and os.access(cand, os.X_OK):
                return os.path.abspath(cand)
        return None

    def _is_ignored(self, rel_path: str) -> bool:
        parts = rel_path.split(os.sep)
        for part in parts:
            for pat in self.ignore_patterns:
                if fnmatch.fnmatch(part, pat):
                    return True
        for pat in self.ignore_patterns:
            if fnmatch.fnmatch(rel_path, pat):
                return True
        return False

    # ── Scanning & Discovery ──────────────────────────────────────────────
    def scan(self) -> Dict[str, List[str]]:
        """Recursively scans source directory and categorizes all files."""
        self.scanned_py.clear()
        self.scanned_cython.clear()
        self.scanned_assets.clear()
        self.scanned_ignored.clear()

        if not os.path.isdir(self.source_dir):
            raise NotADirectoryError(f"Source directory not found: {self.source_dir}")

        for root, dirs, files in os.walk(self.source_dir):
            rel_root = os.path.relpath(root, self.source_dir)
            if rel_root != "." and self._is_ignored(rel_root):
                dirs[:] = []
                continue

            for f in files:
                full_path = os.path.join(root, f)
                rel_file = os.path.relpath(full_path, self.source_dir)

                if self._is_ignored(rel_file):
                    self.scanned_ignored.append(full_path)
                    continue

                if f.endswith(".py"):
                    self.scanned_py.append(full_path)
                elif f.endswith(".pyx") or f.endswith(".pxd") or (
                    (f.endswith(".so") or f.endswith(".pyd")) and not f.startswith("lib")
                ):
                    self.scanned_cython.append(full_path)
                else:
                    self.scanned_assets.append(full_path)

        self.scanned_py.sort()
        self.scanned_cython.sort()
        self.scanned_assets.sort()

        return {
            "python": self.scanned_py,
            "cython": self.scanned_cython,
            "assets": self.scanned_assets,
            "ignored": self.scanned_ignored,
        }

    # ── Project Indexing ──────────────────────────────────────────────────
    def build_project_index(self) -> Dict[str, Any]:
        """Pre-scans discovered Python files to extract symbols, classes, fields, and initializers."""
        self.project_index.clear()
        self.class_index.clear()

        for py_path in self.scanned_py:
            try:
                with open(py_path, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source)
            except Exception:
                continue

            rel_py = os.path.relpath(py_path, self.source_dir)
            base_no_ext, _ = os.path.splitext(rel_py)
            mod_dot = base_no_ext.replace(os.sep, ".")
            mod_base = os.path.basename(base_no_ext)

            exported_symbols = []
            classes_in_file = []

            for stmt in tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    exported_symbols.append(stmt.name)
                elif isinstance(stmt, ast.ClassDef):
                    exported_symbols.append(stmt.name)
                    classes_in_file.append(stmt)
                elif isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            exported_symbols.append(target.id)
                elif isinstance(stmt, ast.AnnAssign):
                    if isinstance(stmt.target, ast.Name):
                        exported_symbols.append(stmt.target.id)

            mod_entry = {
                "file": py_path,
                "rel_path": rel_py,
                "symbols": exported_symbols,
            }

            self.project_index[py_path] = mod_entry
            self.project_index[rel_py] = mod_entry
            self.project_index[base_no_ext] = mod_entry
            self.project_index[mod_dot] = mod_entry
            self.project_index[mod_base] = mod_entry
            self.project_index[f".{mod_base}"] = mod_entry
            self.project_index[f"..{mod_base}"] = mod_entry

            # Process classes into class_index
            type_env = TypeEnvironment()
            for cls_stmt in classes_in_file:
                try:
                    tr = ClassTransformer(cls_stmt, type_env, syntax=self.syntax, class_index=self.class_index)
                    tr.analyze()
                    self.class_index[cls_stmt.name] = {
                        "fields": tr.fields,
                        "field_initializers": tr.field_initializers,
                        "methods": tr.methods,
                    }
                except Exception:
                    pass

        return self.project_index

    # ── File Transpilation ────────────────────────────────────────────────
    def transpile_all(self) -> Dict[str, str]:
        """Translates all scanned Python files into corresponding .nz or .mq files."""
        os.makedirs(self.output_dir, exist_ok=True)
        if not self.project_index:
            self.build_project_index()

        transpiler = Transpiler(
            foreign_mode=self.foreign_mode,
            workspace_root=self.workspace_root,
            source_root=self.source_dir,
            syntax=self.syntax,
            project_index=self.project_index,
            class_index=self.class_index,
        )

        for py_path in self.scanned_py:
            rel_py = os.path.relpath(py_path, self.source_dir)
            base_rel, _ = os.path.splitext(rel_py)
            out_path = os.path.join(self.output_dir, f"{base_rel}{self.target_ext}")
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            try:
                transpiled_code = transpiler.transpile_file(py_path, out_path)
                self.transpiled_files[py_path] = out_path
            except Exception as e:
                # Fault-tolerant fallback: log error and emit diagnostic stub
                err_msg = str(e)
                self.transpile_errors.append({
                    "source": py_path,
                    "target": out_path,
                    "error": err_msg,
                })
                fallback_content = (
                    f"// ── Nizam Transpilation Notice ───────────────────────────────────\n"
                    f"// Source: {rel_py}\n"
                    f"// Note: Could not auto-transpile dynamically. Error: {err_msg}\n"
                    f"// Fallback module stub preserved for project integrity.\n\n"
                    f"fn __module_fallback() as bool:\n"
                    f"    return False\n"
                )
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(fallback_content)
                self.transpiled_files[py_path] = out_path

        return self.transpiled_files

    # ── Asset & Extension Replication ─────────────────────────────────────
    def replicate_assets(self) -> List[str]:
        """Copies non-code assets into the destination directory."""
        if not self.copy_assets:
            return []

        for asset_path in self.scanned_assets:
            rel_asset = os.path.relpath(asset_path, self.source_dir)
            dest_path = os.path.join(self.output_dir, rel_asset)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            try:
                shutil.copy2(asset_path, dest_path)
                self.copied_assets.append(dest_path)
            except Exception as e:
                sys.stderr.write(f"Warning: Failed to copy asset {asset_path}: {e}\n")

        return self.copied_assets

    def replicate_extensions(self) -> List[str]:
        """Copies compiled .so / .pyd libraries and Cython sources to destination."""
        if not self.copy_extensions:
            return []

        for ext_path in self.scanned_cython:
            rel_ext = os.path.relpath(ext_path, self.source_dir)
            dest_path = os.path.join(self.output_dir, rel_ext)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            try:
                shutil.copy2(ext_path, dest_path)
                self.copied_extensions.append(dest_path)
            except Exception as e:
                sys.stderr.write(f"Warning: Failed to copy extension {ext_path}: {e}\n")

        return self.copied_extensions

    # ── Cython Native Bridging ────────────────────────────────────────────
    def bridge_cython_extensions(self) -> List[Dict[str, Any]]:
        """Synthesizes typed .nz/.mq bridge modules for discovered Cython extensions."""
        if not self.bridge_cython:
            return []

        # Find unique Cython module base names
        cython_modules: Dict[str, Dict[str, Any]] = {}
        for ext_path in self.scanned_cython:
            rel_ext = os.path.relpath(ext_path, self.source_dir)
            rel_dir = os.path.dirname(rel_ext)
            filename = os.path.basename(rel_ext)

            # Strip cpython ABI suffix if present: mod.cpython-312-x86_64-linux-gnu.so -> mod
            parts = filename.split(".")
            mod_name = parts[0]

            key = os.path.join(rel_dir, mod_name)
            if key not in cython_modules:
                cython_modules[key] = {
                    "module_name": mod_name,
                    "rel_dir": rel_dir,
                    "files": [],
                    "pyx_path": None,
                    "so_path": None,
                }
            cython_modules[key]["files"].append(ext_path)
            if filename.endswith(".pyx"):
                cython_modules[key]["pyx_path"] = ext_path
            elif filename.endswith(".so") or filename.endswith(".pyd"):
                cython_modules[key]["so_path"] = ext_path

        for key, info in cython_modules.items():
            mod_name = info["module_name"]
            rel_dir = info["rel_dir"]
            bridge_file = os.path.join(self.output_dir, rel_dir, f"{mod_name}{self.target_ext}")
            os.makedirs(os.path.dirname(bridge_file), exist_ok=True)

            # Extract declared functions from .pyx if available
            declared_functions = []
            declared_classes = []
            if info["pyx_path"] and os.path.exists(info["pyx_path"]):
                try:
                    with open(info["pyx_path"], "r", encoding="utf-8") as f:
                        for line in f:
                            l = line.strip()
                            if l.startswith("cdef class ") or l.startswith("class "):
                                cls_part = l.split("(")[0].split(":")[0].split()[-1].strip()
                                if cls_part.isidentifier() and not cls_part.startswith("_") and cls_part not in declared_classes:
                                    declared_classes.append(cls_part)
                            elif l.startswith("def ") or l.startswith("cdef ") or l.startswith("cpdef "):
                                if " class " not in l and "(" in l:
                                    # extract fn name
                                    fn_part = l.split("(")[0].split()[-1].strip()
                                    if fn_part.isidentifier() and not fn_part.startswith("_") and fn_part not in declared_functions:
                                        declared_functions.append(fn_part)
                except Exception:
                    pass

            # Generate bridge module content
            bridge_lines = [
                f"// ── Cython Native Bridge: {mod_name} ────────────────────────────────",
                f"// Auto-generated by Nizam Project Transpiler for native interop",
            ]
            if info["so_path"]:
                bridge_lines.append(f"// Target Shared Library: {os.path.basename(info['so_path'])}")
            bridge_lines.append("")

            if declared_functions:
                for fn in declared_functions:
                    bridge_lines.append(f"extern[python] fn {fn}(...) as ptr")
                bridge_lines.append("")

            if declared_classes:
                for cls in declared_classes:
                    bridge_lines.append(f"struct {cls}:")
                    bridge_lines.append(f"    public var _py_handle as ptr")
                    bridge_lines.append("")

            if not declared_functions and not declared_classes:
                # Generic dynamic extension export
                bridge_lines.append(f"extern[python] fn {mod_name}_init() as ptr")
                bridge_lines.append("")

            bridge_content = "\n".join(bridge_lines) + "\n"
            with open(bridge_file, "w", encoding="utf-8") as f:
                f.write(bridge_content)

            self.bridged_extensions.append({
                "module": mod_name,
                "bridge_file": bridge_file,
                "functions": declared_functions,
                "classes": declared_classes,
                "so_path": info["so_path"],
            })

        return self.bridged_extensions

    def _locate_mantiq_lib_dir(self) -> str:
        candidates = [
            os.path.join(self.workspace_root, "mantiq"),
            os.path.join(self.workspace_root, "stage3"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../mantiq")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../stage3")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../mantiq")),
        ]
        for cand in candidates:
            if os.path.isdir(cand) and (
                os.path.exists(os.path.join(cand, "runtime.c"))
                or os.path.exists(os.path.join(cand, "libtree-sitter-mantiq.so"))
            ):
                return os.path.abspath(cand)
        return self.workspace_root

    # ── Check Mode Verification ───────────────────────────────────────────
    def check_all(self, timeout: int = 5, max_file_size: int = 40 * 1024) -> Dict[str, Any]:
        """Runs `mantiq check` across generated files without compiling binary."""
        if not self.check or not self.mantiq_bin:
            return self.check_results

        self.check_results = {"passed": [], "failed": [], "skipped": []}
        mantiq_lib_dir = self._locate_mantiq_lib_dir()

        for src_py, out_nz in self.transpiled_files.items():
            if not os.path.exists(out_nz):
                continue

            file_size = os.path.getsize(out_nz)
            if file_size > max_file_size:
                self.check_results["skipped"].append({
                    "file": out_nz,
                    "reason": f"File size ({file_size} bytes) exceeds verification threshold ({max_file_size} bytes)",
                })
                continue

            cmd = [self.mantiq_bin, "check", out_nz, "--lib-dir", mantiq_lib_dir]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=self.output_dir)
                if proc.returncode == 0:
                    self.check_results["passed"].append(out_nz)
                else:
                    self.check_results["failed"].append({
                        "file": out_nz,
                        "stdout": proc.stdout.strip(),
                        "stderr": proc.stderr.strip(),
                    })
            except subprocess.TimeoutExpired:
                self.check_results["failed"].append({
                    "file": out_nz,
                    "stdout": "",
                    "stderr": f"Check timed out (> {timeout}s)",
                })
            except Exception as e:
                self.check_results["failed"].append({
                    "file": out_nz,
                    "stdout": "",
                    "stderr": str(e),
                })

        return self.check_results

    # ── Manifest & Report Generation ──────────────────────────────────────
    def generate_manifest(self) -> Dict[str, Any]:
        """Emits transpile_manifest.json and TRANSPILATION_REPORT.md in output directory."""
        manifest = {
            "source_dir": self.source_dir,
            "output_dir": self.output_dir,
            "syntax": self.syntax,
            "summary": {
                "scanned_python": len(self.scanned_py),
                "scanned_cython": len(self.scanned_cython),
                "scanned_assets": len(self.scanned_assets),
                "scanned_ignored": len(self.scanned_ignored),
                "transpiled_success": len(self.transpiled_files) - len(self.transpile_errors),
                "transpiled_fallback": len(self.transpile_errors),
                "copied_assets": len(self.copied_assets),
                "copied_extensions": len(self.copied_extensions),
                "bridged_cython_modules": len(self.bridged_extensions),
                "check_passed": len(self.check_results["passed"]),
                "check_failed": len(self.check_results["failed"]),
            },
            "transpiled_files": self.transpiled_files,
            "transpile_errors": self.transpile_errors,
            "bridged_extensions": self.bridged_extensions,
            "check_results": self.check_results,
        }

        manifest_path = os.path.join(self.output_dir, "transpile_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Generate markdown report
        report_lines = [
            f"# Nizam Project Transpilation Report",
            f"",
            f"**Source Directory:** `{self.source_dir}`  ",
            f"**Output Directory:** `{self.output_dir}`  ",
            f"**Target Syntax:** `{self.syntax}` (`{self.target_ext}`)  ",
            f"",
            f"## 📊 Summary Statistics",
            f"",
            f"| Category | Count |",
            f"| :--- | :--- |",
            f"| Python Sources Discovered | **{len(self.scanned_py)}** |",
            f"| Successfully Transpiled | **{len(self.transpiled_files) - len(self.transpile_errors)}** |",
            f"| Fallback Stubs (Dynamic) | **{len(self.transpile_errors)}** |",
            f"| Cython Extensions Discovered | **{len(self.scanned_cython)}** |",
            f"| Cython Bridges Synthesized | **{len(self.bridged_extensions)}** |",
            f"| Assets Replicated | **{len(self.copied_assets)}** |",
        ]
        if self.check:
            report_lines.extend([
                f"| Compiler Check Passed | **{len(self.check_results['passed'])}** |",
                f"| Compiler Check Failed | **{len(self.check_results['failed'])}** |",
            ])

        if self.bridged_extensions:
            report_lines.extend([
                f"",
                f"## 🔌 Cython & Native Extension Bridges",
                f"",
                f"| Module | Bridge File | Functions |",
                f"| :--- | :--- | :--- |",
            ])
            for b in self.bridged_extensions:
                fn_str = ", ".join(b["functions"]) if b["functions"] else "(dynamic)"
                rel_bridge = os.path.relpath(b["bridge_file"], self.output_dir)
                report_lines.append(f"| `{b['module']}` | `{rel_bridge}` | `{fn_str}` |")

        report_lines.append("")
        report_path = os.path.join(self.output_dir, "TRANSPILATION_REPORT.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

        return manifest

    # ── High-Level Pipeline ───────────────────────────────────────────────
    def execute(self) -> Dict[str, Any]:
        """Runs full project transpilation pipeline."""
        self.scan()
        self.build_project_index()
        self.transpile_all()
        self.replicate_assets()
        self.replicate_extensions()
        self.bridge_cython_extensions()
        if self.check:
            self.check_all()
        return self.generate_manifest()

# ── Convenience Helper ──────────────────────────────────────────────────
def transpile_project(
    source_dir: str,
    output_dir: str,
    syntax: str = "nz",
    check: bool = False,
    copy_assets: bool = True,
    copy_extensions: bool = True,
    bridge_cython: bool = True,
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Transpiles a Python project directory tree into native Nizam or Mantiq code."""
    transpiler = ProjectTranspiler(
        source_dir=source_dir,
        output_dir=output_dir,
        syntax=syntax,
        check=check,
        copy_assets=copy_assets,
        copy_extensions=copy_extensions,
        bridge_cython=bridge_cython,
        workspace_root=workspace_root,
    )
    return transpiler.execute()
