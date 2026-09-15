# ── Imports ────────────────────────────────────────────────────────────
import ast
from typing import Optional, Dict, Any, List

# ── Type Translation Constants ─────────────────────────────────────────
PRIMITIVE_TYPE_MAP: Dict[str, str] = {
    "int": "i64",
    "i8": "i8",
    "i16": "i16",
    "i32": "i32",
    "i64": "i64",
    "u8": "u8",
    "u16": "u16",
    "u32": "u32",
    "u64": "u64",
    "float": "f64",
    "f32": "f32",
    "f64": "f64",
    "bool": "bool",
    "str": "String",
    "bytes": "List[u8]",
    "None": "void",
    "NoneType": "void",
    "Any": "PyObject",
    "object": "PyObject",
    "PyObject": "PyObject",
    "cstr": "cstr",
    "ptr": "ptr",
    "void": "void",
}

CONTAINER_TYPE_MAP: Dict[str, str] = {
    "list": "List",
    "List": "List",
    "dict": "Dict",
    "Dict": "Dict",
    "set": "Set",
    "Set": "Set",
    "Optional": "Option",
}

# ── Type Environment & Inference Engine ─────────────────────────────────
class TypeEnvironment:
    """Manages lexical scopes, variable type tracking, and PEP 484/526 resolution."""

    def __init__(self, parent: Optional["TypeEnvironment"] = None):
        self.parent = parent
        self.symbols: Dict[str, str] = {}
        self.function_signatures: Dict[str, Dict[str, Any]] = {}
        self.struct_definitions: Dict[str, Dict[str, str]] = {}

    def new_child(self) -> "TypeEnvironment":
        return TypeEnvironment(parent=self)

    def define(self, name: str, type_name: str) -> None:
        self.symbols[name] = type_name

    def lookup(self, name: str) -> Optional[str]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def define_struct(self, name: str, fields: Dict[str, str]) -> None:
        self.struct_definitions[name] = fields

    def register_struct(self, name: str, fields: Dict[str, str]) -> None:
        self.define_struct(name, fields)

    def lookup_struct(self, name: str) -> Optional[Dict[str, str]]:
        if name in self.struct_definitions:
            return self.struct_definitions[name]
        if self.parent:
            return self.parent.lookup_struct(name)
        return None

    def register_function(self, name: str, params: List[tuple], return_type: str) -> None:
        self.function_signatures[name] = {
            "params": params,
            "return_type": return_type,
        }

    def lookup_function(self, name: str) -> Optional[Dict[str, Any]]:
        if name in self.function_signatures:
            return self.function_signatures[name]
        if self.parent:
            return self.parent.lookup_function(name)
        return None

    # ── AST Type Annotation Resolution ─────────────────────────────────
    def resolve_annotation(self, node: Optional[ast.AST]) -> str:
        """Resolves an AST type annotation node into a canonical Nizam type."""
        if node is None:
            return "void"

        # Direct name: int, str, float, etc.
        if isinstance(node, ast.Name):
            return PRIMITIVE_TYPE_MAP.get(node.id, node.id)

        # Constant (e.g. None)
        if isinstance(node, ast.Constant):
            if node.value is None:
                return "void"
            if isinstance(node.value, str):
                return PRIMITIVE_TYPE_MAP.get(node.value, node.value)

        # Subscripts: List[int], Dict[str, int], Optional[str], Union[int, None]
        if isinstance(node, ast.Subscript):
            base = self.resolve_annotation(node.value)
            container_name = CONTAINER_TYPE_MAP.get(base, base)

            # Python 3.9+ slice is the element or tuple of elements
            slice_node = node.slice
            if isinstance(slice_node, ast.Tuple):
                type_args = [self.resolve_annotation(elt) for elt in slice_node.elts]
            else:
                type_args = [self.resolve_annotation(slice_node)]

            if container_name == "Optional" or (base in ("Union", "typing.Union") and "void" in type_args):
                real_types = [t for t in type_args if t != "void"]
                inner = real_types[0] if real_types else "PyObject"
                return f"Option[{inner}]"

            if container_name in ("List", "Dict", "Set"):
                inner = ", ".join(type_args)
                return f"{container_name}[{inner}]"

            if base in ("Callable", "typing.Callable") and len(type_args) >= 2:
                # Callable[[Arg1, Arg2], Ret]
                return f"fn({', '.join(type_args[:-1])}) as {type_args[-1]}"

            return f"{container_name}[{', '.join(type_args)}]"

        # Binary operator: int | None (PEP 604 Union syntax)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = self.resolve_annotation(node.left)
            right = self.resolve_annotation(node.right)
            if left == "void":
                return f"Option[{right}]"
            if right == "void":
                return f"Option[{left}]"
            return f"Union[{left}, {right}]"

        # Attribute: typing.List, etc.
        if isinstance(node, ast.Attribute):
            return PRIMITIVE_TYPE_MAP.get(node.attr, node.attr)

        return "PyObject"

    # ── Expression Type Inference ───────────────────────────────────────
    def infer_expression_type(self, node: ast.AST) -> str:
        """Infers the resulting Nizam type of a given Python expression."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "bool"
            if isinstance(node.value, int):
                return "i64"
            if isinstance(node.value, float):
                return "f64"
            if isinstance(node.value, str):
                return "String"
            if node.value is None:
                return "void"

        if isinstance(node, ast.Name):
            val = self.lookup(node.id)
            if val:
                return val
            return "PyObject"

        if isinstance(node, ast.BinOp):
            left_t = self.infer_expression_type(node.left)
            right_t = self.infer_expression_type(node.right)
            if left_t == "String" or right_t == "String":
                return "String"
            if left_t == "f64" or right_t == "f64":
                return "f64"
            if left_t in ("i64", "i32") and right_t in ("i64", "i32"):
                return "i64"
            return "i64"

        if isinstance(node, ast.UnaryOp):
            return self.infer_expression_type(node.operand)

        if isinstance(node, ast.Compare):
            return "bool"

        if isinstance(node, ast.List):
            if node.elts:
                elem_t = self.infer_expression_type(node.elts[0])
                return f"List[{elem_t}]"
            return "List[i64]"

        if isinstance(node, ast.Dict):
            if node.keys and node.values and node.keys[0] is not None:
                k_t = self.infer_expression_type(node.keys[0])
                v_t = self.infer_expression_type(node.values[0])
                return f"Dict[{k_t}, {v_t}]"
            return "Dict[String, String]"

        if isinstance(node, ast.JoinedStr):
            return "String"

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in ("int", "len", "range"):
                    return "i64"
                if func_name == "float":
                    return "f64"
                if func_name == "str":
                    return "String"
                if func_name in ("bool", "hasattr"):
                    return "bool"
                if func_name == "setattr":
                    return "void"
                if func_name == "getattr" and len(node.args) >= 2:
                    obj_t = self.infer_expression_type(node.args[0])
                    attr_arg = node.args[1]
                    if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str):
                        s_info = self.lookup_struct(obj_t)
                        if s_info and attr_arg.value in s_info:
                            return s_info[attr_arg.value]
                sig = self.lookup_function(func_name)
                if sig:
                    return sig["return_type"]
                # Constructor pattern (e.g. CounterWidget(...))
                if func_name[0].isupper():
                    return func_name

            elif isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                sig = self.lookup_function(method_name)
                if sig:
                    return sig["return_type"]
                if method_name in ("startswith", "endswith", "has") or method_name.startswith("is_") or method_name.startswith("has_"):
                    return "bool"
                if method_name in ("lower", "upper", "strip", "replace", "join"):
                    return "String"
                if method_name == "split":
                    return "List[String]"
                if method_name in ("keys", "to_list"):
                    return "List[PyObject]"

        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                var_type = self.lookup(node.value.id)
                if var_type:
                    struct_info = self.lookup_struct(var_type)
                    if struct_info and node.attr in struct_info:
                        return struct_info[node.attr]

        return "PyObject"
