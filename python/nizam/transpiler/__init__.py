# ── Imports ────────────────────────────────────────────────────────────
import ast
import os
from typing import Optional
from .types import TypeEnvironment
from .visitor import NizamTranspilerVisitor

# ── Public API ─────────────────────────────────────────────────────────
class Transpiler:
    """Python-to-Nizam Transpiler frontend."""

    def __init__(
        self,
        foreign_mode: str = "extern",
        workspace_root: Optional[str] = None,
        type_env: Optional[TypeEnvironment] = None,
    ):
        self.foreign_mode = foreign_mode
        self.workspace_root = workspace_root
        self.type_env = type_env or TypeEnvironment()

    def transpile(self, source_code: str) -> str:
        """Parses Python source code and returns canonical Nizam code."""
        parsed_ast = ast.parse(source_code)
        visitor = NizamTranspilerVisitor(
            type_env=self.type_env,
            foreign_mode=self.foreign_mode,
            workspace_root=self.workspace_root,
        )
        return visitor.visit(parsed_ast)

    def transpile_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """Transpiles a Python file to Nizam, optionally writing to an output file."""
        with open(input_path, "r", encoding="utf-8") as f:
            source = f.read()

        transpiled = self.transpile(source)

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(transpiled)

        return transpiled

def transpile(
    source_code: str,
    foreign_mode: str = "extern",
    workspace_root: Optional[str] = None,
) -> str:
    """Convenience helper to transpile a Python code string to Nizam."""
    return Transpiler(foreign_mode=foreign_mode, workspace_root=workspace_root).transpile(source_code)

def transpile_file(
    input_path: str,
    output_path: Optional[str] = None,
    foreign_mode: str = "extern",
    workspace_root: Optional[str] = None,
) -> str:
    """Convenience helper to transpile a Python file to Nizam."""
    return Transpiler(foreign_mode=foreign_mode, workspace_root=workspace_root).transpile_file(input_path, output_path)

from .builder import ProjectBuilder, build_project
from .wasm_loader import WasmLoaderGenerator

__all__ = [
    "Transpiler",
    "transpile",
    "transpile_file",
    "ProjectBuilder",
    "build_project",
    "WasmLoaderGenerator",
]
