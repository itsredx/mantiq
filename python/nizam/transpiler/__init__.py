# ── Imports ────────────────────────────────────────────────────────────
import ast
import os
from typing import Any, Dict, Optional
from .types import TypeEnvironment
from .visitor import NizamTranspilerVisitor

# ── Public API ─────────────────────────────────────────────────────────
class Transpiler:
    """Python-to-Nizam Transpiler frontend."""

    def __init__(
        self,
        foreign_mode: str = "extern",
        workspace_root: Optional[str] = None,
        source_root: Optional[str] = None,
        type_env: Optional[TypeEnvironment] = None,
        syntax: str = "nz",
        project_index: Optional[Dict[str, Any]] = None,
        class_index: Optional[Dict[str, Any]] = None,
    ):
        self.foreign_mode = foreign_mode
        self.workspace_root = workspace_root
        self.source_root = source_root
        self.type_env = type_env or TypeEnvironment()
        self.syntax = "mq" if syntax.lower() in ("mq", "mantiq") else "nz"
        self.project_index = project_index or {}
        self.class_index = class_index or {}

    def transpile(self, source_code: str, current_file_path: Optional[str] = None) -> str:
        """Parses Python source code and returns canonical Nizam or Mantiq code."""
        parsed_ast = ast.parse(source_code)
        visitor = NizamTranspilerVisitor(
            type_env=self.type_env,
            foreign_mode=self.foreign_mode,
            workspace_root=self.workspace_root,
            source_root=self.source_root,
            syntax=self.syntax,
            project_index=self.project_index,
            class_index=self.class_index,
            current_file_path=current_file_path,
        )
        return visitor.visit(parsed_ast)

    def transpile_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """Transpiles a Python file to Nizam or Mantiq, optionally writing to an output file."""
        with open(input_path, "r", encoding="utf-8") as f:
            source = f.read()

        transpiled = self.transpile(source, current_file_path=input_path)

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(transpiled)

        return transpiled

def transpile(
    source_code: str,
    foreign_mode: str = "extern",
    workspace_root: Optional[str] = None,
    source_root: Optional[str] = None,
    syntax: str = "nz",
    project_index: Optional[Dict[str, Any]] = None,
    class_index: Optional[Dict[str, Any]] = None,
    current_file_path: Optional[str] = None,
) -> str:
    """Convenience helper to transpile a Python code string to Nizam or Mantiq."""
    return Transpiler(
        foreign_mode=foreign_mode,
        workspace_root=workspace_root,
        source_root=source_root,
        syntax=syntax,
        project_index=project_index,
        class_index=class_index,
    ).transpile(source_code, current_file_path=current_file_path)

def transpile_file(
    input_path: str,
    output_path: Optional[str] = None,
    foreign_mode: str = "extern",
    workspace_root: Optional[str] = None,
    source_root: Optional[str] = None,
    syntax: str = "nz",
    project_index: Optional[Dict[str, Any]] = None,
    class_index: Optional[Dict[str, Any]] = None,
) -> str:
    """Convenience helper to transpile a Python file to Nizam or Mantiq."""
    return Transpiler(
        foreign_mode=foreign_mode,
        workspace_root=workspace_root,
        source_root=source_root,
        syntax=syntax,
        project_index=project_index,
        class_index=class_index,
    ).transpile_file(input_path, output_path)

from .builder import ProjectBuilder, build_project
from .wasm_loader import WasmLoaderGenerator
from .project import ProjectTranspiler, transpile_project

__all__ = [
    "Transpiler",
    "transpile",
    "transpile_file",
    "ProjectBuilder",
    "build_project",
    "WasmLoaderGenerator",
    "ProjectTranspiler",
    "transpile_project",
]
