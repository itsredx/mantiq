# ── Imports ─────────────────────────────────────────────────────────────
import os
import sys
import shutil
import subprocess
from typing import List, Optional, Dict, Any
from . import Transpiler
from .wasm_loader import WasmLoaderGenerator

# ── Project Builder & Compiler Driver ───────────────────────────────────
class ProjectBuilder:
    """Orchestrates recursive Python project scanning, transpilation, and native/WASM compilation."""

    def __init__(
        self,
        source_path: str,
        output_path: Optional[str] = None,
        target: str = "native",
        release: bool = False,
        web_loader: bool = False,
        entrypoint: Optional[str] = None,
        foreign_mode: str = "extern",
        workspace_root: Optional[str] = None,
        mantiq_bin: Optional[str] = None,
        build_dir: Optional[str] = None,
    ):
        self.source_path = os.path.abspath(source_path)
        self.target = "wasm32-wasi" if target in ("wasm", "wasm32-wasi") else "native"
        self.release = release
        self.web_loader = web_loader
        self.entrypoint = entrypoint
        self.foreign_mode = foreign_mode
        self.workspace_root = os.path.abspath(workspace_root) if workspace_root else (
            self.source_path if os.path.isdir(self.source_path) else os.path.dirname(self.source_path)
        )
        self.build_dir = build_dir or os.path.join(self.workspace_root, "build", "transpiled")
        self.output_path = output_path
        self.mantiq_bin = mantiq_bin or self._locate_mantiq_binary()
        self.mantiq_dir = self._locate_mantiq_lib_dir()

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

    def _locate_mantiq_lib_dir(self) -> str:
        candidates = [
            os.path.join(self.workspace_root, "mantiq"),
            os.path.join(self.workspace_root, "stage3"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../mantiq")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
        ]
        for cand in candidates:
            if os.path.isdir(cand) and os.path.exists(os.path.join(cand, "runtime.c")):
                return os.path.abspath(cand)
        return self.workspace_root

    def discover_source_files(self) -> List[str]:
        """Finds all target Python source files within the project."""
        if os.path.isfile(self.source_path):
            return [self.source_path]

        found = []
        skip_dirs = {".git", ".svn", "__pycache__", ".agents", "venv", ".venv", "build", "dist", "node_modules"}
        for root, dirs, files in os.walk(self.source_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for file in files:
                if file.endswith(".py"):
                    found.append(os.path.join(root, file))
        return sorted(found)

    def determine_entrypoint(self, sources: List[str]) -> str:
        """Determines the main entrypoint file to build."""
        if self.entrypoint:
            full_entry = os.path.abspath(self.entrypoint)
            if os.path.exists(full_entry):
                return full_entry
            # Check relative to source_path
            rel_entry = os.path.join(self.source_path, self.entrypoint)
            if os.path.exists(rel_entry):
                return rel_entry

        # Standard entrypoint conventions
        if os.path.isfile(self.source_path):
            return self.source_path

        for cand in ("main.py", "app.py", "__main__.py"):
            full = os.path.join(self.source_path, cand)
            if full in sources:
                return full

        return sources[0] if sources else self.source_path

    def transpile_all(self, sources: List[str]) -> Dict[str, str]:
        """Transpiles all discovered Python files into the build directory."""
        os.makedirs(self.build_dir, exist_ok=True)
        source_dir = self.source_path if os.path.isdir(self.source_path) else os.path.dirname(self.source_path)
        transpiler = Transpiler(
            foreign_mode=self.foreign_mode,
            workspace_root=self.workspace_root,
            source_root=source_dir,
        )

        transpiled_map = {}
        for src in sources:
            rel_path = os.path.relpath(src, source_dir)
            base_rel, _ = os.path.splitext(rel_path)
            out_nz = os.path.join(self.build_dir, f"{base_rel}.nz")
            os.makedirs(os.path.dirname(out_nz), exist_ok=True)

            transpiled_code = transpiler.transpile_file(src, out_nz)
            transpiled_map[src] = out_nz

        return transpiled_map

    def build(self) -> Dict[str, Any]:
        """Executes the full pipeline: scan -> transpile -> compile native/wasm binary."""
        sources = self.discover_source_files()
        if not sources:
            raise FileNotFoundError(f"No Python source files found in {self.source_path}")

        entry_src = self.determine_entrypoint(sources)
        transpiled_map = self.transpile_all(sources)
        entry_nz = transpiled_map[entry_src]

        # Determine output binary destination
        if not self.output_path:
            dist_dir = os.path.join(self.workspace_root, "dist")
            os.makedirs(dist_dir, exist_ok=True)
            entry_base = os.path.splitext(os.path.basename(entry_src))[0]
            ext = ".wasm" if self.target == "wasm32-wasi" else ""
            self.output_path = os.path.join(dist_dir, f"{entry_base}{ext}")
        else:
            self.output_path = os.path.abspath(self.output_path)
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

        if not self.mantiq_bin:
            raise RuntimeError("Could not locate native mantiq/nizam compiler executable.")

        # Build command invocation
        cmd = [self.mantiq_bin, "build", entry_nz, "-o", self.output_path, "--lib-dir", self.mantiq_dir]
        if self.target == "wasm32-wasi":
            cmd.extend(["--target", "wasm32-wasi"])

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Nizam compilation failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")

        # Post-processing: Stripping symbols in release mode (Native)
        if self.release and self.target == "native" and os.path.exists(self.output_path):
            strip_tool = shutil.which("strip")
            if strip_tool:
                subprocess.run([strip_tool, "--strip-all", self.output_path], capture_output=True)

        # Post-processing: WebAssembly loader generation
        loader_files = None
        if self.target == "wasm32-wasi" and self.web_loader:
            out_dir = os.path.dirname(self.output_path)
            wasm_filename = os.path.basename(self.output_path)
            app_title = os.path.splitext(wasm_filename)[0].replace("_", " ").title()
            generator = WasmLoaderGenerator(output_dir=out_dir, app_title=app_title)
            loader_files = generator.generate(wasm_filename=wasm_filename)

        bin_size = os.path.getsize(self.output_path) if os.path.exists(self.output_path) else 0

        return {
            "success": True,
            "target": self.target,
            "entrypoint": entry_src,
            "entry_nz": entry_nz,
            "transpiled_count": len(transpiled_map),
            "transpiled_files": list(transpiled_map.values()),
            "output_path": self.output_path,
            "binary_size": bin_size,
            "loader_files": loader_files,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

def build_project(
    source_path: str,
    output_path: Optional[str] = None,
    target: str = "native",
    release: bool = False,
    web_loader: bool = False,
    entrypoint: Optional[str] = None,
    foreign_mode: str = "extern",
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience helper to execute the ProjectBuilder pipeline."""
    builder = ProjectBuilder(
        source_path=source_path,
        output_path=output_path,
        target=target,
        release=release,
        web_loader=web_loader,
        entrypoint=entrypoint,
        foreign_mode=foreign_mode,
        workspace_root=workspace_root,
    )
    return builder.build()
