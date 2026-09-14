# ── Nizam In-Process Loader & PEP 451 Import Hook ───────────────────────
"""PEP 451 import hook and concurrency-safe on-the-fly compiler for Nizam."""

import os
import sys
import time
import fcntl
import shutil
import hashlib
import subprocess
import importlib.abc
import importlib.machinery
from typing import Optional, Sequence

def _find_nizam_compiler() -> str:
    """Locate the Nizam compiler binary."""
    # 1. Explicit environment override
    if "NIZAM_BIN" in os.environ and os.path.isfile(os.environ["NIZAM_BIN"]):
        return os.environ["NIZAM_BIN"]

    # 2. PATH resolution
    which_nizam = shutil.which("nizam")
    if which_nizam:
        return which_nizam

    # 3. User local directory
    user_local = os.path.expanduser("~/.local/bin/nizam")
    if os.path.isfile(user_local) and os.access(user_local, os.X_OK):
        return user_local

    # 4. Workspace fallback search
    curr = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        cand1 = os.path.join(curr, "stage3", "mantiq")
        if os.path.isfile(cand1) and os.access(cand1, os.X_OK):
            return cand1
        cand2 = os.path.join(curr, "nizam")
        if os.path.isfile(cand2) and os.access(cand2, os.X_OK):
            return cand2
        cand3 = os.path.join(curr, "mantiq", "nizam")
        if os.path.isfile(cand3) and os.access(cand3, os.X_OK):
            return cand3
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent

    raise FileNotFoundError("Could not locate Nizam compiler binary ('nizam'). Set NIZAM_BIN environment variable.")

class NizamLoader(importlib.abc.Loader):
    """Compiles Nizam (.nz/.mq) sources on-the-fly into PEP 384 abi3 shared libraries."""

    def __init__(self, fullname: str, source_path: str):
        self.fullname = fullname
        self.source_path = os.path.abspath(source_path)
        self._cached_so: Optional[str] = None
        self._ext_loader: Optional[importlib.machinery.ExtensionFileLoader] = None

    def _ensure_compiled(self) -> str:
        if self._cached_so and os.path.isfile(self._cached_so):
            return self._cached_so

        # 1. Compute SHA-256 fingerprint of source code
        with open(self.source_path, "rb") as f:
            src_bytes = f.read()
        src_hash = hashlib.sha256(src_bytes).hexdigest()[:16]

        # 2. Derive cache directory
        src_dir = os.path.dirname(self.source_path)
        cache_dir = os.path.join(src_dir, "__pycache__", ".nizam_cache")
        try:
            os.makedirs(cache_dir, exist_ok=True)
            test_file = os.path.join(cache_dir, ".write_test")
            with open(test_file, "w") as f:
                f.write("1")
            os.remove(test_file)
        except OSError:
            cache_dir = os.path.expanduser("~/.cache/nizam")
            os.makedirs(cache_dir, exist_ok=True)

        leaf = self.fullname.rpartition(".")[2]
        cached_so = os.path.join(cache_dir, f"{leaf}.{src_hash}.abi3.so")
        lock_file = os.path.join(cache_dir, f"{leaf}.lock")

        # 3. Atomic lockfile protocol protecting against multi-process compile races
        if not os.path.isfile(cached_so):
            with open(lock_file, "w") as lock_fd:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
                try:
                    # Double-check inside exclusive lock
                    if not os.path.isfile(cached_so):
                        tmp_dir = os.path.join(cache_dir, f"tmp_{os.getpid()}_{time.time_ns()}")
                        os.makedirs(tmp_dir, exist_ok=True)
                        tmp_so = os.path.join(tmp_dir, f"{leaf}.abi3.so")
                        compiler_bin = _find_nizam_compiler()

                        # Check for lib-dir in workspace
                        workspace_root = os.path.dirname(os.path.dirname(compiler_bin))
                        lib_dir_flag = []
                        if os.path.isdir(os.path.join(workspace_root, "mantiq")):
                            lib_dir_flag = ["--lib-dir", os.path.join(workspace_root, "mantiq")]
                        elif os.path.isdir(os.path.join(os.path.dirname(compiler_bin), "mantiq")):
                            lib_dir_flag = ["--lib-dir", os.path.join(os.path.dirname(compiler_bin), "mantiq")]

                        cmd = [compiler_bin, "build", self.source_path, "--target", "python-ext", "-o", tmp_so] + lib_dir_flag
                        res = subprocess.run(cmd, capture_output=True, text=True)
                        if res.returncode != 0 or not os.path.isfile(tmp_so):
                            shutil.rmtree(tmp_dir, ignore_errors=True)
                            raise ImportError(
                                f"Failed to compile Nizam source '{self.source_path}' into native extension:\n"
                                f"Command: {' '.join(cmd)}\n"
                                f"STDOUT:\n{res.stdout}\n"
                                f"STDERR:\n{res.stderr}"
                            )

                        # Atomic rename guarantees no worker sees a partially written .so
                        os.replace(tmp_so, cached_so)

                        # Also atomically move .pyi type stub if generated
                        tmp_pyi = os.path.join(tmp_dir, f"{leaf}.pyi")
                        cached_pyi = os.path.join(cache_dir, f"{leaf}.{src_hash}.pyi")
                        if os.path.isfile(tmp_pyi):
                            os.replace(tmp_pyi, cached_pyi)

                        shutil.rmtree(tmp_dir, ignore_errors=True)
                finally:
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

        self._cached_so = cached_so
        return cached_so

    def create_module(self, spec):
        cached_so = self._ensure_compiled()
        spec.origin = cached_so
        self._ext_loader = importlib.machinery.ExtensionFileLoader(self.fullname, cached_so)
        return self._ext_loader.create_module(spec)

    def exec_module(self, module):
        cached_so = self._ensure_compiled()
        if self._ext_loader is None:
            self._ext_loader = importlib.machinery.ExtensionFileLoader(self.fullname, cached_so)
        self._ext_loader.exec_module(module)

class NizamFinder(importlib.abc.MetaPathFinder):
    """PEP 451 MetaPathFinder resolving imports of .nz and .mq source files."""

    def find_spec(self, fullname: str, path: Optional[Sequence[str]] = None, target=None):
        leaf = fullname.rpartition(".")[2]
        search_dirs = list(path) if path is not None else sys.path

        for directory in search_dirs:
            if not directory or not os.path.isdir(directory):
                continue
            cand_nz = os.path.join(directory, f"{leaf}.nz")
            if os.path.isfile(cand_nz):
                loader = NizamLoader(fullname, cand_nz)
                return importlib.machinery.ModuleSpec(fullname, loader, origin=cand_nz)
            cand_mq = os.path.join(directory, f"{leaf}.mq")
            if os.path.isfile(cand_mq):
                loader = NizamLoader(fullname, cand_mq)
                return importlib.machinery.ModuleSpec(fullname, loader, origin=cand_mq)

        return None

def install():
    """Install the Nizam import hook into sys.meta_path if not already present."""
    if not any(isinstance(f, NizamFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, NizamFinder())
