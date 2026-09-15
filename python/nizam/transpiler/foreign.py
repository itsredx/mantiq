# ── Imports ─────────────────────────────────────────────────────────────
import os
import ast
from typing import Dict, List, Optional, Set, Tuple, Any

# ── Dependency Classifier ───────────────────────────────────────────────
class DependencyClassifier:
    """Classifies module dependencies into local (transpilable) vs foreign (Python FFI)."""

    STANDARD_LIBRARIES: Set[str] = {
        "math", "os", "sys", "json", "time", "random", "re", "shutil",
        "hashlib", "urllib", "collections", "itertools", "functools",
        "pathlib", "datetime", "subprocess", "io", "glob", "csv",
        "sqlite3", "socket", "threading", "logging", "builtins", "ctypes",
        "struct", "copy", "decimal", "fractions", "bisect", "heapq",
    }

    THIRD_PARTY_LIBRARIES: Set[str] = {
        "PySide6", "PyQt5", "PyQt6", "numpy", "scipy", "pandas",
        "requests", "torch", "PIL", "cv2", "flask", "fastapi",
        "matplotlib", "pydantic", "sqlalchemy", "yaml", "toml",
    }

    def __init__(self, workspace_root: Optional[str] = None, source_root: Optional[str] = None):
        self.workspace_root = os.path.abspath(workspace_root) if workspace_root else os.getcwd()
        self.source_root = os.path.abspath(source_root) if source_root else self.workspace_root

    def is_local_transpilable(self, module_name: str) -> bool:
        """Check if a module exists as a local source file in the workspace or source root."""
        if not module_name:
            return False

        root_pkg = module_name.split(".")[0]
        if root_pkg in self.STANDARD_LIBRARIES or root_pkg in self.THIRD_PARTY_LIBRARIES:
            return False

        # Look for local .py or .nz file candidates across workspace and source roots
        rel_path = module_name.replace(".", os.sep)
        roots = [self.workspace_root]
        if self.source_root and self.source_root != self.workspace_root:
            roots.append(self.source_root)

        for root in roots:
            candidates = [
                os.path.join(root, f"{rel_path}.py"),
                os.path.join(root, rel_path, "__init__.py"),
                os.path.join(root, f"{rel_path}.nz"),
                os.path.join(root, f"{rel_path}.mq"),
            ]
            if any(os.path.isfile(cand) for cand in candidates):
                return True
        return False

    def is_foreign(self, module_name: str) -> bool:
        """Return True if the module requires foreign Python FFI bridging."""
        return not self.is_local_transpilable(module_name)

# ── Foreign Function Signature ───────────────────────────────────────────
class ForeignFunctionSignature:
    """Type signature representation for an external Python function or method."""

    def __init__(
        self,
        name: str,
        module: str,
        params: Optional[List[Tuple[str, str]]] = None,
        return_type: str = "PyObject",
        is_method: bool = False,
    ):
        self.name = name
        self.module = module
        self.params = params or []
        self.return_type = return_type
        self.is_method = is_method

    def to_nizam_extern_line(self) -> str:
        """Format signature as a Nizam extern function declaration."""
        param_strs = [f"{pname} as {ptype}" for pname, ptype in self.params]
        params_formatted = ", ".join(param_strs)
        return f"fn {self.name}({params_formatted}) as {self.return_type}"

# ── Foreign Module Registry ──────────────────────────────────────────────
class ForeignModuleRegistry:
    """Manages external Python imports, call tracking, and extern stub synthesis."""

    # Curated catalog of static signatures for common Python standard library functions
    KNOWN_SIGNATURES: Dict[str, Dict[str, Tuple[List[Tuple[str, str]], str]]] = {
        "math": {
            "sqrt": ([("x", "f64")], "f64"),
            "pow": ([("base", "f64"), ("exp", "f64")], "f64"),
            "floor": ([("x", "f64")], "f64"),
            "ceil": ([("x", "f64")], "f64"),
            "hypot": ([("x", "f64"), ("y", "f64")], "f64"),
            "isnan": ([("x", "f64")], "bool"),
            "isinf": ([("x", "f64")], "bool"),
            "fabs": ([("x", "f64")], "f64"),
            "sin": ([("x", "f64")], "f64"),
            "cos": ([("x", "f64")], "f64"),
            "tan": ([("x", "f64")], "f64"),
            "asin": ([("x", "f64")], "f64"),
            "acos": ([("x", "f64")], "f64"),
            "atan": ([("x", "f64")], "f64"),
            "atan2": ([("y", "f64"), ("x", "f64")], "f64"),
            "log": ([("x", "f64")], "f64"),
            "log10": ([("x", "f64")], "f64"),
            "log2": ([("x", "f64")], "f64"),
            "exp": ([("x", "f64")], "f64"),
        },
        "os.path": {
            "join": ([("a", "cstr"), ("b", "cstr")], "cstr"),
            "dirname": ([("p", "cstr")], "cstr"),
            "basename": ([("p", "cstr")], "cstr"),
            "exists": ([("p", "cstr")], "bool"),
            "isfile": ([("p", "cstr")], "bool"),
            "isdir": ([("p", "cstr")], "bool"),
        },
        "builtins": {
            "abs": ([("x", "i64")], "i64"),
        },
        "sys": {
            "exit": ([("code", "i64")], "void"),
        },
        "json": {
            "loads": ([("s", "cstr")], "PyObject"),
            "dumps": ([("obj", "PyObject")], "cstr"),
        },
    }

    def __init__(self, classifier: Optional[DependencyClassifier] = None):
        self.classifier = classifier or DependencyClassifier()
        self.imported_modules: Dict[str, str] = {}  # alias_or_name -> canonical_module
        self.imported_symbols: Dict[str, Tuple[str, str]] = {}  # symbol_name -> (canonical_module, orig_name)
        self.recorded_calls: Dict[str, Dict[str, ForeignFunctionSignature]] = {}  # module -> {func_name: sig}

    def register_import(self, module_name: str, alias: Optional[str] = None):
        """Record an 'import <module> [as <alias>]' statement."""
        key = alias or module_name
        self.imported_modules[key] = module_name
        if module_name not in self.recorded_calls:
            self.recorded_calls[module_name] = {}

    def register_import_from(self, module_name: str, names: List[Tuple[str, Optional[str]]]):
        """Record a 'from <module> import <name> [as <alias>]' statement."""
        for name, alias in names:
            sym = alias or name
            self.imported_symbols[sym] = (module_name, name)
        if module_name not in self.recorded_calls:
            self.recorded_calls[module_name] = {}

    def resolve_foreign_call(self, target: str) -> Optional[Tuple[str, str]]:
        """Resolve a function or method call to its canonical foreign (module, func_name) pair."""
        # 1. Direct symbol import (e.g. sqrt from 'from math import sqrt')
        if target in self.imported_symbols:
            return self.imported_symbols[target]

        # 2. Module attribute call (e.g. math.sqrt or osp.join)
        if "." in target:
            mod_part, _, func_part = target.rpartition(".")
            if mod_part in self.imported_modules:
                return (self.imported_modules[mod_part], func_part)
            # Check submodule import like PySide6.QtWidgets
            if mod_part in self.classifier.STANDARD_LIBRARIES or mod_part in self.classifier.THIRD_PARTY_LIBRARIES:
                return (mod_part, func_part)

        return None

    def record_call(
        self,
        module: str,
        func_name: str,
        arg_types: Optional[List[str]] = None,
        return_type: Optional[str] = None,
    ) -> ForeignFunctionSignature:
        """Record an invoked foreign function and infer/lookup its signature."""
        if module not in self.recorded_calls:
            self.recorded_calls[module] = {}

        if func_name in self.recorded_calls[module]:
            return self.recorded_calls[module][func_name]

        # Check known signature catalog
        if module in self.KNOWN_SIGNATURES and func_name in self.KNOWN_SIGNATURES[module]:
            known_params, known_ret = self.KNOWN_SIGNATURES[module][func_name]
            sig = ForeignFunctionSignature(func_name, module, known_params, known_ret)
            self.recorded_calls[module][func_name] = sig
            return sig

        # Fallback dynamic inference
        params = []
        if arg_types:
            for i, atype in enumerate(arg_types):
                params.append((f"arg{i}", atype))
        else:
            params = []

        ret_t = return_type or "PyObject"
        sig = ForeignFunctionSignature(func_name, module, params, ret_t)
        self.recorded_calls[module][func_name] = sig
        return sig

    def generate_extern_blocks(self) -> List[str]:
        """Generate static typed 'extern[python]' declarations for all recorded foreign calls."""
        lines: List[str] = []
        for mod, funcs in sorted(self.recorded_calls.items()):
            if not funcs:
                continue
            lines.append(f'extern[python] "{mod}":')
            for func_name, sig in sorted(funcs.items()):
                lines.append(f"    {sig.to_nizam_extern_line()}")
            lines.append("")
        return lines

    def generate_import_statements(self) -> List[str]:
        """Generate dynamic 'import[python]' declarations for imported foreign modules."""
        lines: List[str] = []
        seen = set()
        for alias, mod in sorted(self.imported_modules.items()):
            if (mod, alias) in seen:
                continue
            seen.add((mod, alias))
            if alias != mod:
                lines.append(f"import[python] {mod} as {alias}")
            else:
                lines.append(f"import[python] {mod}")
        for sym, (mod, orig_name) in sorted(self.imported_symbols.items()):
            if (mod, sym) in seen:
                continue
            seen.add((mod, sym))
            if sym != orig_name:
                lines.append(f"from[python] {mod} import {orig_name} as {sym}")
            else:
                lines.append(f"from[python] {mod} import {orig_name}")
        return lines
