# ── Imports ────────────────────────────────────────────────────────────
import ast
from typing import Dict, List, Optional, Set, Tuple
from .types import TypeEnvironment

# ── PyThra Component Base Classification ───────────────────────────────
PYTHRA_WIDGET_BASES = {"Widget", "StatelessWidget", "StatefulWidget"}
PYTHRA_STATE_BASES = {"State"}

# ── Class & Struct Transformer ─────────────────────────────────────────
class ClassTransformer:
    """Transforms Python class definitions into native Nizam structs and methods."""

    def __init__(self, node: ast.ClassDef, type_env: TypeEnvironment):
        self.node = node
        self.type_env = type_env
        self.class_name = node.name
        self.base_names: List[str] = [self._get_base_name(b) for b in node.bases]
        self.is_widget = any(b in PYTHRA_WIDGET_BASES or "Widget" in b for b in self.base_names)
        self.is_state = any(b in PYTHRA_STATE_BASES or "State" in b for b in self.base_names)

        self.fields: Dict[str, str] = {}
        self.field_defaults: Dict[str, str] = {}
        self.field_initializers: Dict[str, ast.AST] = {}
        self.init_node: Optional[ast.FunctionDef] = None
        self.methods: List[ast.FunctionDef] = []

    def _get_base_name(self, base_node: ast.AST) -> str:
        if isinstance(base_node, ast.Name):
            return base_node.id
        if isinstance(base_node, ast.Attribute):
            return base_node.attr
        if isinstance(base_node, ast.Subscript):
            return self._get_base_name(base_node.value)
        return ""

    def analyze(self) -> None:
        """Inspects the class body to collect fields, constructors, and methods."""
        # 1. Inspect class body for class-level variable annotations
        for item in self.node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                field_name = item.target.id
                field_type = self.type_env.resolve_annotation(item.annotation)
                self.fields[field_name] = field_type
                if item.value:
                    self.field_initializers[field_name] = item.value

            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        field_name = target.id
                        field_type = self.type_env.infer_expression_type(item.value)
                        self.fields[field_name] = field_type
                        self.field_initializers[field_name] = item.value

            elif isinstance(item, ast.FunctionDef):
                if item.name == "__init__":
                    self.init_node = item
                else:
                    self.methods.append(item)
                    m_params = []
                    for arg in item.args.args:
                        arg_type = self.type_env.resolve_annotation(arg.annotation) if arg.annotation else "i64"
                        m_params.append((arg.arg, arg_type))
                    m_ret_type = self.type_env.resolve_annotation(item.returns) if item.returns else "void"
                    self.type_env.register_function(item.name, m_params, m_ret_type)
                    self.type_env.register_function(f"{self.class_name}.{item.name}", m_params, m_ret_type)

        # 2. Inspect __init__ for self.<field> assignments and param annotations
        if self.init_node:
            init_param_types = {}
            for arg in self.init_node.args.args:
                if arg.arg != "self" and arg.annotation:
                    init_param_types[arg.arg] = self.type_env.resolve_annotation(arg.annotation)

            for stmt in self.init_node.body:
                # self.x = val
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                            field_name = target.attr
                            self.field_initializers[field_name] = stmt.value
                            if field_name not in self.fields:
                                # Check if assigned from a constructor parameter
                                if isinstance(stmt.value, ast.Name) and stmt.value.id in init_param_types:
                                    self.fields[field_name] = init_param_types[stmt.value.id]
                                else:
                                    self.fields[field_name] = self.type_env.infer_expression_type(stmt.value)

                # self.x: int = val
                elif isinstance(stmt, ast.AnnAssign):
                    if isinstance(stmt.target, ast.Attribute) and isinstance(stmt.target.value, ast.Name) and stmt.target.value.id == "self":
                        field_name = stmt.target.attr
                        if stmt.value:
                            self.field_initializers[field_name] = stmt.value
                        field_type = self.type_env.resolve_annotation(stmt.annotation)
                        self.fields[field_name] = field_type

        # Register the completed struct definition in TypeEnvironment
        self.type_env.define(self.class_name, self.class_name)
        self.type_env.define_struct(self.class_name, self.fields)

    def generate_struct_definition(self, visitor: "ast.NodeVisitor") -> List[str]:
        """Emits the Nizam struct header, public fields, and factory constructor."""
        lines = []
        lines.append(f"struct {self.class_name}:")

        # Emit struct fields
        if not self.fields:
            lines.append("    public var _unused as i64")
        else:
            for field_name, field_type in self.fields.items():
                lines.append(f"    public var {field_name} as {field_type}")

        # Emit factory constructor (fn init)
        lines.append("")
        constructor_code = self._generate_constructor(visitor)
        for cline in constructor_code:
            lines.append(f"    {cline}")

        return lines

    def _generate_constructor(self, visitor: "ast.NodeVisitor") -> List[str]:
        lines = []
        params_str_list = []
        assignments = []

        if self.init_node:
            defaults_offset = len(self.init_node.args.args) - len(self.init_node.args.defaults)
            for i, arg in enumerate(self.init_node.args.args):
                if arg.arg == "self":
                    continue
                arg_type = self.fields.get(arg.arg, "i64")
                if arg.annotation:
                    arg_type = self.type_env.resolve_annotation(arg.annotation)

                # Default value if any
                default_val = None
                default_idx = i - defaults_offset
                if default_idx >= 0:
                    default_node = self.init_node.args.defaults[default_idx]
                    default_val = visitor.visit_expr(default_node)

                if default_val:
                    params_str_list.append(f"{arg.arg} as {arg_type} = {default_val}")
                else:
                    params_str_list.append(f"{arg.arg} as {arg_type}")
        else:
            # Default empty or field-based constructor
            for fname, ftype in self.fields.items():
                params_str_list.append(f"{fname} as {ftype}")

        # Build assignments for each struct field
        for fname, ftype in self.fields.items():
            if fname in self.field_initializers:
                val_node = self.field_initializers[fname]
                val_str = visitor.visit_expr(val_node)
                assignments.append(f"{fname} = {val_str}")
            elif self.init_node and any(arg.arg == fname for arg in self.init_node.args.args):
                assignments.append(f"{fname} = {fname}")
            else:
                default_expr = self._get_type_default(ftype)
                assignments.append(f"{fname} = {default_expr}")

        param_str = ", ".join(params_str_list)
        assign_str = ", ".join(assignments)

        lines.append(f"public fn init({param_str}) as {self.class_name}:")
        if self.init_node:
            for stmt in self.init_node.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    func = stmt.value.func
                    if isinstance(func, ast.Attribute) and func.attr == "__init__":
                        if isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name) and func.value.func.id == "super":
                            lines.append("    // super().__init__()")
        lines.append(f"    return {self.class_name}({assign_str})")
        return lines

    def _get_type_default(self, ftype: str) -> str:
        if ftype in ("i64", "i32", "u64", "u32", "isize", "usize"):
            return "0 to i64"
        if ftype in ("f64", "f32"):
            return "0.0"
        if ftype == "bool":
            return "False"
        if ftype == "String":
            return 'String.make("" to cstr)'
        if ftype == "cstr":
            return '"" to cstr'
        return "None"
