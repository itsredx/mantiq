# ── Imports ────────────────────────────────────────────────────────────
import ast
from typing import List, Optional, Set, Dict, Tuple, Any
from .types import TypeEnvironment, PRIMITIVE_TYPE_MAP
from .classes import ClassTransformer
from .foreign import DependencyClassifier, ForeignModuleRegistry, ForeignFunctionSignature

# ── Operator Mappings ──────────────────────────────────────────────────
BIN_OP_MAP = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "/",
    ast.Mod: "%",
    ast.BitAnd: "&",
    ast.BitOr: "|",
    ast.BitXor: "^",
    ast.LShift: "<<",
    ast.RShift: ">>",
}

CMP_OP_MAP = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Is: "==",
    ast.IsNot: "!=",
    ast.In: "in",
}

UNARY_OP_MAP = {
    ast.UAdd: "+",
    ast.USub: "-",
    ast.Not: "not ",
    ast.Invert: "~",
}

# ── AST Node Visitor ──────────────────────────────────────────────────
class NizamTranspilerVisitor(ast.NodeVisitor):
    """Visits Python AST nodes and emits canonical, statically-typed Nizam code."""

    def __init__(
        self,
        type_env: Optional[TypeEnvironment] = None,
        foreign_mode: str = "extern",
        workspace_root: Optional[str] = None,
        source_root: Optional[str] = None,
        dependency_classifier: Optional[DependencyClassifier] = None,
        foreign_registry: Optional[ForeignModuleRegistry] = None,
        syntax: str = "nz",
        project_index: Optional[Dict[str, Any]] = None,
        class_index: Optional[Dict[str, Any]] = None,
        current_file_path: Optional[str] = None,
    ):
        self.indent_level = 0
        self.type_env = type_env or TypeEnvironment()
        self.foreign_mode = foreign_mode
        self.workspace_root = workspace_root
        self.source_root = source_root
        self.syntax = "mq" if syntax.lower() in ("mq", "mantiq") else "nz"
        self.project_index = project_index or {}
        self.class_index = class_index or {}
        self.current_file_path = current_file_path
        self.local_classes: Dict[str, Any] = {}
        self.classifier = dependency_classifier or DependencyClassifier(workspace_root=workspace_root, source_root=source_root)
        self.foreign_registry = foreign_registry or ForeignModuleRegistry(self.classifier)
        self.output_lines: List[str] = []
        self.declared_variables: Set[str] = set()
        self.needs_printf: bool = False
        self.needs_math: bool = False
        self.has_main: bool = False
        self.top_level_stmts: List[ast.stmt] = []
        self.current_class: Optional[str] = None
        self.current_class_fields: Set[str] = set()

    def emit(self, line: str = ""):
        if not line:
            self.output_lines.append("")
        else:
            indent = "    " * self.indent_level
            self.output_lines.append(f"{indent}{line}")

    # ── Module Handling ────────────────────────────────────────────────
    def visit_Module(self, node: ast.Module) -> str:
        # Pre-pass 1: Register imports (foreign vs local)
        for stmt in node.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if self.classifier.is_foreign(alias.name):
                        self.foreign_registry.register_import(alias.name, alias.asname)
            elif isinstance(stmt, ast.ImportFrom):
                if stmt.level == 0 and stmt.module and stmt.module not in self.project_index and self.classifier.is_foreign(stmt.module):
                    names = [(alias.name, alias.asname) for alias in stmt.names]
                    self.foreign_registry.register_import_from(stmt.module, names)

        # Pre-pass 2: Register local functions and classes into type_env
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef):
                self._pre_register_function(stmt)
            elif isinstance(stmt, ast.ClassDef):
                transformer = ClassTransformer(
                    stmt,
                    self.type_env,
                    syntax=self.syntax,
                    class_index=self.class_index,
                    local_classes=self.local_classes,
                )
                transformer.analyze()
                self.local_classes[stmt.name] = transformer
                if self.class_index is not None:
                    self.class_index[stmt.name] = {
                        "fields": transformer.fields,
                        "field_initializers": transformer.field_initializers,
                        "methods": transformer.methods,
                    }

        # Pre-pass 3: Scan calls to detect foreign calls and record signatures
        for sub_node in ast.walk(node):
            if isinstance(sub_node, ast.Call):
                self._pre_register_foreign_call(sub_node)

        # Separate function/class definitions from top-level scripts
        script_stmts = []
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
                self.visit(stmt)
            elif isinstance(stmt, ast.If) and self._is_main_guard(stmt):
                # if __name__ == '__main__': ...
                self.has_main = True
                self.emit()
                self.emit("// ── Application Entrypoint ──────────────────────────────────────────")
                self.emit("fn main() as i32:")
                self.indent_level += 1
                for sub_stmt in stmt.body:
                    self.visit(sub_stmt)
                self.emit("return 0")
                self.indent_level -= 1
            else:
                script_stmts.append(stmt)

        # If there are top-level script statements and no main was generated:
        if script_stmts and not self.has_main:
            self.has_main = True
            self.emit()
            self.emit("// ── Application Entrypoint ──────────────────────────────────────────")
            self.emit("fn main() as i32:")
            self.indent_level += 1
            for stmt in script_stmts:
                self.visit(stmt)
            self.emit("return 0")
            self.indent_level -= 1

        # Prepend headers if required
        headers = []
        if self.needs_printf:
            headers.append("extern fn printf(format as cstr, ...) as i32")
        if self.needs_math and "math" not in self.foreign_registry.recorded_calls:
            headers.append("from std.math import pow, sqrt")

        # Foreign Interop declarations
        if self.foreign_mode in ("extern", "auto"):
            extern_lines = self.foreign_registry.generate_extern_blocks()
            if extern_lines:
                headers.extend(extern_lines)
        elif self.foreign_mode == "import":
            import_lines = self.foreign_registry.generate_import_statements()
            if import_lines:
                headers.extend(import_lines)

        if headers:
            while headers and headers[-1] == "":
                headers.pop()
            headers.append("")
            self.output_lines = headers + self.output_lines

        return "\n".join(self.output_lines).rstrip() + "\n"

    def _is_main_guard(self, node: ast.If) -> bool:
        """Detects if __name__ == '__main__': guard."""
        test = node.test
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], (ast.Eq, ast.Is)):
            left = test.left
            right = test.comparators[0]
            if isinstance(left, ast.Name) and left.id == "__name__":
                if isinstance(right, ast.Constant) and right.value == "__main__":
                    return True
        return False

    def _pre_register_function(self, node: ast.FunctionDef):
        params = []
        for arg in node.args.args:
            arg_type = self.type_env.resolve_annotation(arg.annotation) if arg.annotation else "i64"
            params.append((arg.arg, arg_type))
        ret_type = self.type_env.resolve_annotation(node.returns) if node.returns else "void"
        self.type_env.register_function(node.name, params, ret_type)

    def _pre_register_foreign_call(self, call_node: ast.Call):
        target = None
        if isinstance(call_node.func, ast.Name):
            target = call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            target = self._get_attr_chain(call_node.func)

        if target:
            resolved = self.foreign_registry.resolve_foreign_call(target)
            if resolved:
                mod, func_name = resolved
                arg_types = [self.type_env.infer_expression_type(arg) for arg in call_node.args]
                sig = self.foreign_registry.record_call(mod, func_name, arg_types)
                # Register in type_env so assignment inference picks up the return type
                self.type_env.register_function(func_name, sig.params, sig.return_type)

    def _get_attr_chain(self, node: ast.AST) -> Optional[str]:
        parts = []
        curr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            return ".".join(reversed(parts))
        return None

    # ── Imports ────────────────────────────────────────────────────────
    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in ("typing", "typing_extensions", "collections.abc"):
                continue  # Type hints only
            if self.classifier.is_foreign(alias.name):
                # Foreign module is handled in headers via extern[python] or import[python]
                continue
            else:
                self.emit(f"import {alias.name}")

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module in ("typing", "typing_extensions", "collections.abc"):
            return
        if node.level == 0 and node.module and node.module not in self.project_index and self.classifier.is_foreign(node.module):
            # Foreign symbols handled via extern[python] or import[python]
            return

        # Reconstruct relative prefix from node.level
        dots = "." * (node.level or 0)
        full_module = dots + (node.module or "")

        is_wildcard = any(alias.name == "*" for alias in node.names)
        if is_wildcard:
            expanded_symbols: List[str] = []
            mod_candidates: List[str] = []
            if full_module:
                mod_candidates.append(full_module)
            if node.module:
                mod_candidates.append(node.module)
                mod_candidates.append(node.module.lstrip("."))
                if "." in node.module:
                    mod_candidates.append(node.module.split(".")[-1])

            for cand in mod_candidates:
                if cand in self.project_index:
                    syms = self.project_index[cand].get("symbols", [])
                    if syms:
                        expanded_symbols = syms
                        break

            if expanded_symbols:
                for sym in expanded_symbols:
                    if sym and sym[0].isupper() and not sym.isupper():
                        self.type_env.register_struct(sym, {})
                names = ", ".join(expanded_symbols)
                self.emit(f"from {full_module} import {names}")
                return
            else:
                # Tree-sitter mantiq grammar cannot parse `*`. If wildcard expansion has no known symbols,
                # emit a clean import statement to avoid syntax failure:
                clean_mod = full_module.lstrip(".")
                if clean_mod:
                    self.emit(f"import {clean_mod}")
                return

        for alias in node.names:
            if alias.name and alias.name[0].isupper() and not alias.name.isupper():
                self.type_env.register_struct(alias.name, {})
        names = ", ".join(alias.name for alias in node.names)
        if full_module:
            self.emit(f"from {full_module} import {names}")

    # ── Class Definitions ──────────────────────────────────────────────
    def visit_ClassDef(self, node: ast.ClassDef):
        transformer = ClassTransformer(
            node,
            self.type_env,
            syntax=self.syntax,
            class_index=self.class_index,
            local_classes=self.local_classes,
        )
        transformer.analyze()

        self.emit()
        kind_label = "Class" if self.syntax == "mq" else "Struct"
        self.emit(f"// ── {kind_label}: {transformer.class_name} ─────────────────────────────────────────────")
        if self.syntax == "mq":
            lines = transformer.generate_class_definition(self)
            for line in lines:
                self.emit(line)
        else:
            lines = transformer.generate_struct_definition(self)
            for line in lines:
                self.emit(line)

        # Instance methods inside the struct/class block
        self.current_class = transformer.class_name
        self.current_class_fields = set(transformer.fields.keys())

        self.indent_level += 1
        for method in transformer.methods:
            self.visit_FunctionDef(method)
        self.indent_level -= 1

        self.current_class = None
        self.current_class_fields = set()

    # ── Function Definitions ───────────────────────────────────────────
    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.emit()
        func_title = f"Method: {self.current_class}.{node.name}" if self.current_class else f"Function: {node.name}"
        self.emit(f"// ── {func_title} ───────────────────────────────────────────────")

        prev_vars = self.declared_variables
        self.declared_variables = set()
        child_env = self.type_env.new_child()
        old_env = self.type_env
        self.type_env = child_env

        params_strs = []
        for arg in node.args.args:
            if arg.arg == "self" and self.current_class:
                self.type_env.define("self", self.current_class)
                self.declared_variables.add("self")
                params_strs.append(f"self as ptr[{self.current_class}]")
            else:
                arg_type = self.type_env.resolve_annotation(arg.annotation) if arg.annotation else "i64"
                self.type_env.define(arg.arg, arg_type)
                self.declared_variables.add(arg.arg)
                if arg.arg == "self":
                    params_strs.append("self")
                else:
                    params_strs.append(f"{arg.arg} as {arg_type}")

        ret_type = self.type_env.resolve_annotation(node.returns) if node.returns else "void"
        param_str = ", ".join(params_strs)

        if self.syntax == "nz" and self.current_class:
            fn_prefix = "public fn" if not node.name.startswith("_") else "fn"
        else:
            fn_prefix = "fn"

        if ret_type == "void":
            self.emit(f"{fn_prefix} {node.name}({param_str}):")
        else:
            self.emit(f"{fn_prefix} {node.name}({param_str}) as {ret_type}:")

        self.indent_level += 1

        body_stmts = node.body
        # Check for docstring
        if body_stmts and isinstance(body_stmts[0], ast.Expr) and isinstance(body_stmts[0].value, ast.Constant):
            if isinstance(body_stmts[0].value.value, str):
                for doc_line in body_stmts[0].value.value.strip().split("\n"):
                    self.emit(f"// {doc_line.strip()}")
                body_stmts = body_stmts[1:]

        for stmt in body_stmts:
            # Check for super().__init__(...)
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                func = stmt.value.func
                if isinstance(func, ast.Attribute) and func.attr == "__init__":
                    if isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id == "super":
                        self.emit("// super().__init__()")
                        continue
            self.visit(stmt)

        self.indent_level -= 1
        self.type_env = old_env
        self.declared_variables = prev_vars

    # ── Variable Assignments ───────────────────────────────────────────
    def visit_AnnAssign(self, node: ast.AnnAssign):
        target_name = self._get_target_name(node.target)
        val_str = self.visit_expr(node.value) if node.value else "None"
        annotated_type = self.type_env.resolve_annotation(node.annotation)

        if target_name:
            self.type_env.define(target_name, annotated_type)
            if target_name not in self.declared_variables:
                self.declared_variables.add(target_name)
                self.emit(f"var {target_name} as {annotated_type} = {val_str}")
            else:
                self.emit(f"{target_name} = {val_str}")
        else:
            target_str = self.visit_expr(node.target)
            self.emit(f"{target_str} = {val_str}")

    def visit_Assign(self, node: ast.Assign):
        val_str = self.visit_expr(node.value)
        inferred_type = self.type_env.infer_expression_type(node.value)

        for target in node.targets:
            target_name = self._get_target_name(target)
            if target_name:
                if target_name not in self.declared_variables:
                    self.declared_variables.add(target_name)
                    self.type_env.define(target_name, inferred_type)
                    self.emit(f"var {target_name} as {inferred_type} = {val_str}")
                else:
                    self.emit(f"{target_name} = {val_str}")
            else:
                target_str = self.visit_expr(target)
                self.emit(f"{target_str} = {val_str}")

    def visit_AugAssign(self, node: ast.AugAssign):
        target_str = self.visit_expr(node.target)
        op_str = BIN_OP_MAP.get(type(node.op), "+")
        val_str = self.visit_expr(node.value)
        self.emit(f"{target_str} {op_str}= {val_str}")

    def _get_target_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        return None

    # ── Control Flow ───────────────────────────────────────────────────
    def visit_If(self, node: ast.If):
        cond_str = self.visit_expr(node.test)
        self.emit(f"if {cond_str}:")
        self.indent_level += 1
        for stmt in node.body:
            self.visit(stmt)
        self.indent_level -= 1

        curr = node
        while curr.orelse:
            if len(curr.orelse) == 1 and isinstance(curr.orelse[0], ast.If):
                curr = curr.orelse[0]
                elif_cond = self.visit_expr(curr.test)
                self.emit(f"elif {elif_cond}:")
                self.indent_level += 1
                for stmt in curr.body:
                    self.visit(stmt)
                self.indent_level -= 1
            else:
                self.emit("else:")
                self.indent_level += 1
                for stmt in curr.orelse:
                    self.visit(stmt)
                self.indent_level -= 1
                break

    def visit_While(self, node: ast.While):
        cond_str = self.visit_expr(node.test)
        self.emit(f"while {cond_str}:")
        self.indent_level += 1
        for stmt in node.body:
            self.visit(stmt)
        self.indent_level -= 1

    def visit_For(self, node: ast.For):
        iter_node = node.iter

        # Special case: for k, v in d.items() or for (k, v) in d.items()
        if (
            isinstance(iter_node, ast.Call)
            and isinstance(iter_node.func, ast.Attribute)
            and iter_node.func.attr == "items"
            and isinstance(node.target, (ast.Tuple, ast.List))
            and len(node.target.elts) == 2
        ):
            dict_expr = self.visit_expr(iter_node.func.value)
            k_name = self.visit_expr(node.target.elts[0])
            v_name = self.visit_expr(node.target.elts[1])

            self.emit(f"for {k_name} in {dict_expr}.keys():")
            self.indent_level += 1
            self.emit(f"let {v_name} = {dict_expr}[{k_name}]")
            for stmt in node.body:
                self.visit(stmt)
            self.indent_level -= 1
            return

        target_str = self.visit_expr(node.target)

        # Special case: for i in range(...)
        if isinstance(iter_node, ast.Call) and isinstance(iter_node.func, ast.Name) and iter_node.func.id == "range":
            args = iter_node.args
            if len(args) == 1:
                stop_str = self.visit_expr(args[0])
                self.emit(f"for {target_str} in 0..{stop_str}:")
            elif len(args) >= 2:
                start_str = self.visit_expr(args[0])
                stop_str = self.visit_expr(args[1])
                self.emit(f"for {target_str} in {start_str}..{stop_str}:")
        else:
            iter_str = self.visit_expr(iter_node)
            self.emit(f"for {target_str} in {iter_str}:")

        self.indent_level += 1
        for stmt in node.body:
            self.visit(stmt)
        self.indent_level -= 1

    def visit_Return(self, node: ast.Return):
        if node.value:
            val_str = self.visit_expr(node.value)
            self.emit(f"return {val_str}")
        else:
            self.emit("return")

    def visit_Break(self, node: ast.Break):
        self.emit("break")

    def visit_Continue(self, node: ast.Continue):
        self.emit("continue")

    def visit_Pass(self, node: ast.Pass):
        self.emit("// pass")

    def visit_Expr(self, node: ast.Expr):
        expr_str = self.visit_expr(node.value)
        if expr_str:
            self.emit(expr_str)

    # ── Expression Lowering ────────────────────────────────────────────
    def visit_expr(self, node: ast.AST) -> str:
        if isinstance(node, ast.Constant):
            return self._format_constant(node)
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.BinOp):
            return self._format_binop(node)
        if isinstance(node, ast.UnaryOp):
            op = UNARY_OP_MAP.get(type(node.op), "")
            operand = self.visit_expr(node.operand)
            return f"{op}{operand}"
        if isinstance(node, ast.Compare):
            return self._format_compare(node)
        if isinstance(node, ast.BoolOp):
            op_name = " and " if isinstance(node.op, ast.And) else " or "
            parts = [self.visit_expr(val) for val in node.values]
            return f"({op_name.join(parts)})"
        if isinstance(node, ast.Call):
            return self._format_call(node)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                if self.current_class:
                    return f"(deref self).{node.attr}"
            if isinstance(node.value, ast.Name) and node.value.id == "sys" and node.attr == "argv":
                return "[]"
            return f"{self.visit_expr(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            target = self.visit_expr(node.value)
            slice_idx = self.visit_expr(node.slice)
            return f"{target}[{slice_idx}]"
        if isinstance(node, ast.List):
            elts = [self.visit_expr(e) for e in node.elts]
            return f"[{', '.join(elts)}]"
        if isinstance(node, ast.ListComp):
            return self._format_listcomp(node)
        if isinstance(node, ast.JoinedStr):
            return self._format_joinedstr(node)

        return ""

    def _format_constant(self, node: ast.Constant) -> str:
        val = node.value
        if val is None:
            return "None"
        if isinstance(val, bool):
            return "True" if val else "False"
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, str):
            escaped = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}" to cstr'
        return str(val)

    def _format_binop(self, node: ast.BinOp) -> str:
        left = self.visit_expr(node.left)
        right = self.visit_expr(node.right)
        if isinstance(node.op, ast.Pow):
            self.needs_math = True
            return f"pow({left}, {right})"
        op_str = BIN_OP_MAP.get(type(node.op), "+")
        return f"({left} {op_str} {right})"

    def _format_compare(self, node: ast.Compare) -> str:
        left = self.visit_expr(node.left)
        parts = [left]
        for op, comp in zip(node.ops, node.comparators):
            op_sym = CMP_OP_MAP.get(type(op), "==")
            comp_str = self.visit_expr(comp)
            parts.append(f"{op_sym} {comp_str}")
        return " ".join(parts)

    def _format_call(self, node: ast.Call) -> str:
        # Dynamic introspection: getattr, setattr, hasattr
        if isinstance(node.func, ast.Name):
            if node.func.id == "getattr" and len(node.args) >= 2:
                obj_str = self.visit_expr(node.args[0])
                attr_node = node.args[1]
                if isinstance(attr_node, ast.Constant) and isinstance(attr_node.value, str):
                    return f"{obj_str}.{attr_node.value}"
                else:
                    attr_expr = self.visit_expr(attr_node)
                    return f"{obj_str}.get({attr_expr})"

            elif node.func.id == "setattr" and len(node.args) == 3:
                obj_str = self.visit_expr(node.args[0])
                attr_node = node.args[1]
                val_str = self.visit_expr(node.args[2])
                if isinstance(attr_node, ast.Constant) and isinstance(attr_node.value, str):
                    return f"{obj_str}.{attr_node.value} = {val_str}"
                else:
                    attr_expr = self.visit_expr(attr_node)
                    return f"{obj_str}.set({attr_expr}, {val_str})"

            elif node.func.id == "hasattr" and len(node.args) == 2:
                obj_str = self.visit_expr(node.args[0])
                attr_node = node.args[1]
                if isinstance(attr_node, ast.Constant) and isinstance(attr_node.value, str):
                    return f'{obj_str}.has("{attr_node.value}" to cstr)'
                else:
                    attr_expr = self.visit_expr(attr_node)
                    return f"{obj_str}.has({attr_expr})"

        # Check print(...)
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.needs_printf = True
            return self._format_print_call(node.args)

        # Check len(...)
        if isinstance(node.func, ast.Name) and node.func.id == "len" and len(node.args) == 1:
            arg_str = self.visit_expr(node.args[0])
            return f"{arg_str}.len()"

        # Check str(...)
        if isinstance(node.func, ast.Name) and node.func.id == "str" and len(node.args) == 1:
            arg_str = self.visit_expr(node.args[0])
            return f"{arg_str}.to_string()"

        # Check PyThra set_state(...)
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "set_state") or \
           (isinstance(node.func, ast.Name) and node.func.id == "set_state"):
            if node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Lambda):
                    body_expr = self.visit_expr(arg0.body)
                    return f"{body_expr} /* nizam_ui_mark_dirty(self) */"
                elif isinstance(arg0, ast.Call):
                    call_expr = self.visit_expr(arg0)
                    return f"{call_expr} /* nizam_ui_mark_dirty(self) */"

        # Check super().method(...)
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
            inner_call = node.func.value
            if isinstance(inner_call.func, ast.Name) and inner_call.func.id == "super":
                arg_parts = [self.visit_expr(arg) for arg in node.args]
                args_str = ", ".join(arg_parts)
                return f"super().{node.func.attr}({args_str})"

        # Check dict.get(k, default)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and len(node.args) in (1, 2):
            obj_str = self.visit_expr(node.func.value)
            key_str = self.visit_expr(node.args[0])
            default_str = self.visit_expr(node.args[1]) if len(node.args) == 2 else "None"
            return f"({obj_str}[{key_str}] if {obj_str}.has({key_str}) else {default_str})"

        # Check pop(...)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "pop":
            obj_str = self.visit_expr(node.func.value)
            if node.args:
                arg_str = self.visit_expr(node.args[0])
                return f"{obj_str}.remove({arg_str})"
            else:
                return f"{obj_str}.remove({obj_str}.len() - 1)"

        target = None
        if isinstance(node.func, ast.Name):
            target = node.func.id
        elif isinstance(node.func, ast.Attribute):
            target = self._get_attr_chain(node.func)

        func_str = self.visit_expr(node.func)
        is_foreign = False

        if target and self.foreign_mode in ("extern", "auto"):
            resolved = self.foreign_registry.resolve_foreign_call(target)
            if resolved:
                mod, func_name = resolved
                func_str = func_name
                is_foreign = True

        if not is_foreign and isinstance(node.func, ast.Name):
            if self.type_env.lookup_struct(node.func.id) is not None or (node.func.id and node.func.id[0].isupper() and not node.func.id.isupper()):
                if self.syntax == "mq":
                    func_str = node.func.id
                else:
                    func_str = f"{node.func.id}.init"

        arg_parts = [self.visit_expr(arg) for arg in node.args]
        for kw in node.keywords:
            kw_val = self.visit_expr(kw.value)
            arg_parts.append(f"{kw.arg} = {kw_val}")
        args_str = ", ".join(arg_parts)
        return f"{func_str}({args_str})"

    def _format_print_call(self, args: List[ast.AST]) -> str:
        if not args:
            return 'printf("\\n" to cstr)'

        format_specifiers = []
        call_args = []

        for arg in args:
            arg_type = self.type_env.infer_expression_type(arg)
            expr_str = self.visit_expr(arg)

            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                # Constant string literal
                escaped = arg.value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
                format_specifiers.append(escaped)
            elif arg_type in ("i64", "i32", "int"):
                format_specifiers.append("%lld")
                call_args.append(expr_str)
            elif arg_type in ("f64", "f32", "float"):
                format_specifiers.append("%f")
                call_args.append(expr_str)
            elif arg_type == "bool":
                format_specifiers.append("%s")
                call_args.append(f'("True" to cstr if {expr_str} else "False" to cstr)')
            elif arg_type == "String":
                format_specifiers.append("%s")
                call_args.append(f"{expr_str} to cstr")
            elif arg_type == "cstr":
                format_specifiers.append("%s")
                call_args.append(expr_str)
            else:
                format_specifiers.append("%lld")
                call_args.append(expr_str)

        fmt_str = " ".join(format_specifiers) + "\\n"
        call_args_str = (", " + ", ".join(call_args)) if call_args else ""
        return f'printf("{fmt_str}" to cstr{call_args_str})'

    def _format_joinedstr(self, node: ast.JoinedStr) -> str:
        parts = []
        for val in node.values:
            if isinstance(val, ast.Constant) and isinstance(val.value, str):
                escaped = val.value.replace("\\", "\\\\").replace('"', '\\"')
                parts.append(f'"{escaped}"')
            elif isinstance(val, ast.FormattedValue):
                inner_expr = self.visit_expr(val.value)
                parts.append(f"{inner_expr}.to_string()")
        return " + ".join(parts) if parts else '""'

    def _format_listcomp(self, node: ast.ListComp) -> str:
        elt = self.visit_expr(node.elt)
        if not node.generators:
            return f"[{elt}]"
        gen = node.generators[0]
        target = self.visit_expr(gen.target)
        iter_str = self.visit_expr(gen.iter)

        if gen.ifs:
            cond = self.visit_expr(gen.ifs[0])
            return f"[for {target} in {iter_str}: if {cond}: {elt}]"
        return f"[for {target} in {iter_str}: {elt}]"
