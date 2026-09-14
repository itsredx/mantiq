# ── Imports ────────────────────────────────────────────────────────────
import ast
import os
from typing import Optional
from .types import TypeEnvironment
from .visitor import NizamTranspilerVisitor

# ── Public API ─────────────────────────────────────────────────────────
class Transpiler:
    """Python-to-Nizam Transpiler frontend."""

    def __init__(self):
        self.type_env = TypeEnvironment()

    def transpile(self, source_code: str) -> str:
        """Parses Python source code and returns canonical Nizam code."""
        parsed_ast = ast.parse(source_code)
        visitor = NizamTranspilerVisitor(self.type_env)
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

def transpile(source_code: str) -> str:
    """Convenience helper to transpile a Python code string to Nizam."""
    return Transpiler().transpile(source_code)

def transpile_file(input_path: str, output_path: Optional[str] = None) -> str:
    """Convenience helper to transpile a Python file to Nizam."""
    return Transpiler().transpile_file(input_path, output_path)

__all__ = ["Transpiler", "transpile", "transpile_file"]
