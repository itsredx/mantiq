# ── Imports ─────────────────────────────────────────────────────────────
import os
import sys
import json
import time
import shutil
import hashlib
import subprocess
import importlib.util
import importlib.machinery
from typing import Any, Dict, List, Optional, Union

# ── Compiler Resolution Helper ───────────────────────────────────────────
def _find_compiler() -> str:
    """Locate the Nizam / Mantiq compiler binary."""
    if "NIZAM_BIN" in os.environ and os.path.isfile(os.environ["NIZAM_BIN"]):
        return os.environ["NIZAM_BIN"]

    which_nizam = shutil.which("nizam")
    if which_nizam:
        return which_nizam

    user_local = os.path.expanduser("~/.local/bin/nizam")
    if os.path.isfile(user_local) and os.access(user_local, os.X_OK):
        return user_local

    curr = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        cand1 = os.path.join(curr, "stage3", "mantiq")
        if os.path.isfile(cand1) and os.access(cand1, os.X_OK):
            return cand1
        cand2 = os.path.join(curr, "nizam")
        if os.path.isfile(cand2) and os.access(cand2, os.X_OK):
            return cand2
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent

    raise FileNotFoundError("Could not locate Nizam compiler binary ('nizam' or 'stage3/mantiq').")


def _find_reconciler_nz_source() -> str:
    """Locate the canonical reconciler.nz source file in the workspace."""
    curr = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        cand = os.path.join(curr, "mantiq", "src", "ui", "reconciler.nz")
        if os.path.isfile(cand):
            return cand
        cand2 = os.path.join(curr, "src", "ui", "reconciler.nz")
        if os.path.isfile(cand2):
            return cand2
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent

    raise FileNotFoundError("Could not locate 'reconciler.nz' source file.")

# ── Data Structures ──────────────────────────────────────────────────────
class WidgetNode:
    """Virtual DOM Node representation for UI trees."""

    def __init__(
        self,
        tag: str = "div",
        id: Optional[str] = None,
        key: Optional[str] = None,
        props: Optional[Dict[str, Any]] = None,
        children: Optional[List["WidgetNode"]] = None,
    ):
        self.tag = tag
        self.id = id or f"el_{id(self)}"
        self.key = key or self.id
        self.props = {str(k): str(v) for k, v in (props or {}).items()}
        self.children = children or []

    def to_dict(self) -> Dict[str, Any]:
        """Convert node and all nested children to dictionary."""
        return {
            "id": self.id,
            "type": self.tag,
            "key": self.key,
            "props": self.props,
            "children": [c.to_dict() for c in self.children],
        }

    def to_json(self) -> str:
        """Serialize node to compact JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    def __repr__(self) -> str:
        return f"<WidgetNode tag={self.tag!r} id={self.id!r} key={self.key!r} props={self.props!r} children={len(self.children)}>"

# ── Pure-Python Fallback Reconciler ───────────────────────────────────────
class PythonReconciler:
    """Pure-Python reference implementation of the Virtual DOM reconciliation algorithm."""

    def __init__(self):
        self.id_counter = 0

    def fresh_html_id(self) -> str:
        res = f"el_{self.id_counter}"
        self.id_counter += 1
        return res

    def _diff_props(self, old_props: Dict[str, str], new_props: Dict[str, str]) -> str:
        parts = []
        for k in old_props:
            if k in new_props:
                if old_props[k] != new_props[k]:
                    parts.append(f"{k}={new_props[k]}")
            else:
                parts.append(f"{k}=")
        for k in new_props:
            if k not in old_props:
                parts.append(f"{k}={new_props[k]}")
        return ";".join(sorted(parts))

    def _generate_html_stub(self, node_id: str, tag: str) -> str:
        return f'<div id="{node_id}" data-type="{tag}"></div>'

    def _find_next_stable_id(
        self,
        start_idx: int,
        new_keys: List[str],
        old_key_to_index: Dict[str, int],
        rendered_map: Dict[str, Dict[str, Any]],
    ) -> str:
        for k in new_keys[start_idx:]:
            if k in old_key_to_index and k in rendered_map:
                return rendered_map[k]["html_id"]
        return ""

    def _flatten_tree(
        self,
        node: Dict[str, Any],
        parent_id: str,
        parent_key: str,
        out_map: Dict[str, Dict[str, Any]],
    ) -> str:
        node_id = node.get("id") or node.get("html_id") or ""
        tag = node.get("type") or node.get("widget_type") or node.get("tag") or "div"
        key = node.get("key") or node_id
        props = {str(k): str(v) for k, v in node.get("props", {}).items()}

        children_keys = []
        for child in node.get("children", []):
            child_key = self._flatten_tree(child, node_id, key, out_map)
            children_keys.append(child_key)

        out_map[key] = {
            "html_id": node_id,
            "widget_type": tag,
            "key": key,
            "props": props,
            "children_keys": children_keys,
            "parent_html_id": parent_id,
            "parent_key": parent_key,
        }
        return key

    def reconcile(
        self,
        old_tree: Optional[Dict[str, Any]],
        new_tree: Optional[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        patches: List[Dict[str, str]] = []
        old_map: Dict[str, Dict[str, Any]] = {}
        new_map: Dict[str, Dict[str, Any]] = {}
        rendered_map: Dict[str, Dict[str, Any]] = {}

        old_root_key = self._flatten_tree(old_tree, "root", "root_k", old_map) if old_tree else None
        new_root_key = self._flatten_tree(new_tree, "root", "root_k", new_map) if new_tree else None

        if not old_tree and new_tree and new_root_key:
            self._insert_node_recursive(new_map[new_root_key], "root", "root_k", patches, rendered_map, new_map)
        elif old_tree and not new_tree and old_root_key:
            patches.append({
                "action": "REMOVE",
                "html_id": old_map[old_root_key]["html_id"],
                "payload": "",
            })
        elif old_root_key and new_root_key:
            self._diff_node_recursive(old_root_key, new_map[new_root_key], "root", "root_k", patches, old_map, new_map, rendered_map)

        return patches

    def _insert_node_recursive(
        self,
        node: Dict[str, Any],
        parent_id: str,
        parent_key: str,
        patches: List[Dict[str, str]],
        rendered_map: Dict[str, Dict[str, Any]],
        new_map: Dict[str, Dict[str, Any]],
    ):
        html_id = node["html_id"]
        wtype = node["widget_type"]
        patches.append({
            "action": "INSERT",
            "html_id": html_id,
            "payload": self._generate_html_stub(html_id, wtype),
        })
        rendered_map[html_id] = dict(node)
        is_container = wtype in ("StatefulWidget", "StatelessWidget")
        child_parent = parent_key if is_container else html_id
        self._diff_children_recursive(
            [], node["children_keys"], child_parent, html_id, patches, {}, new_map, rendered_map
        )

    def _diff_children_recursive(
        self,
        old_children_keys: List[str],
        new_children_keys: List[str],
        parent_html_id: str,
        parent_key: str,
        patches: List[Dict[str, str]],
        old_map: Dict[str, Dict[str, Any]],
        new_map: Dict[str, Dict[str, Any]],
        rendered_map: Dict[str, Dict[str, Any]],
    ):
        if not old_children_keys and not new_children_keys:
            return

        old_key_to_index = {k: i for i, k in enumerate(old_children_keys)}
        new_key_to_index = {k: i for i, k in enumerate(new_children_keys)}

        for ok in old_children_keys:
            if ok not in new_key_to_index:
                if ok in old_map:
                    patches.append({
                        "action": "REMOVE",
                        "html_id": old_map[ok]["html_id"],
                        "payload": "",
                    })

        last_placed_old_idx = -1
        for ni, nk in enumerate(new_children_keys):
            if nk in old_key_to_index:
                if nk in old_map:
                    old_data = old_map[nk]
                    new_data = new_map.get(nk, old_data)
                    stub = {
                        "html_id": old_data["html_id"],
                        "widget_type": new_data["widget_type"],
                        "key": nk,
                        "props": new_data["props"],
                        "children_keys": new_data["children_keys"],
                        "parent_html_id": parent_html_id,
                        "parent_key": parent_key,
                    }
                    self._diff_node_recursive(nk, stub, parent_html_id, parent_key, patches, old_map, new_map, rendered_map)

                old_idx = old_key_to_index[nk]
                if old_idx < last_placed_old_idx:
                    if nk in rendered_map:
                        moved = rendered_map[nk]
                        before_id = self._find_next_stable_id(ni + 1, new_children_keys, old_key_to_index, rendered_map)
                        patches.append({
                            "action": "MOVE",
                            "html_id": moved["html_id"],
                            "payload": f"before={before_id}",
                        })
                if old_idx > last_placed_old_idx:
                    last_placed_old_idx = old_idx
            else:
                new_stub = {
                    "html_id": self.fresh_html_id(),
                    "widget_type": new_map[nk]["widget_type"] if nk in new_map else "Unknown",
                    "key": nk,
                    "props": new_map[nk]["props"] if nk in new_map else {},
                    "children_keys": new_map[nk]["children_keys"] if nk in new_map else [],
                    "parent_html_id": parent_html_id,
                    "parent_key": parent_key,
                }
                self._insert_node_recursive(new_stub, parent_html_id, parent_key, patches, rendered_map, new_map)

    def _diff_node_recursive(
        self,
        old_node_key: str,
        new_widget: Dict[str, Any],
        parent_html_id: str,
        parent_key: str,
        patches: List[Dict[str, str]],
        old_map: Dict[str, Dict[str, Any]],
        new_map: Dict[str, Dict[str, Any]],
        rendered_map: Dict[str, Dict[str, Any]],
    ):
        if old_node_key not in old_map:
            self._insert_node_recursive(new_widget, parent_html_id, parent_key, patches, rendered_map, new_map)
            return

        old_data = old_map[old_node_key]
        new_type = new_widget["widget_type"]
        old_type = old_data["widget_type"]
        new_key = new_widget["key"]
        old_key = old_data["key"]

        if new_type != old_type or new_key != old_key:
            stub = self._generate_html_stub(old_data["html_id"], new_type)
            patches.append({
                "action": "REPLACE",
                "html_id": old_data["html_id"],
                "payload": stub,
            })
            rendered_map[new_widget["html_id"]] = {
                "html_id": old_data["html_id"],
                "widget_type": new_type,
                "key": new_key,
                "props": new_widget["props"],
                "children_keys": new_widget["children_keys"],
                "parent_html_id": parent_html_id,
                "parent_key": parent_key,
            }
            return

        html_id = old_data["html_id"]
        prop_payload = self._diff_props(old_data["props"], new_widget["props"])
        is_container = old_type in ("StatefulWidget", "StatelessWidget")

        if not is_container and prop_payload:
            patches.append({
                "action": "UPDATE",
                "html_id": html_id,
                "payload": prop_payload,
            })

        rendered_map[new_key] = {
            "html_id": html_id,
            "widget_type": new_type,
            "key": new_key,
            "props": new_widget["props"],
            "children_keys": new_widget["children_keys"],
            "parent_html_id": parent_html_id,
            "parent_key": parent_key,
        }

        child_parent = parent_key if is_container else html_id
        self._diff_children_recursive(
            old_data["children_keys"],
            new_widget["children_keys"],
            child_parent,
            new_widget["html_id"],
            patches,
            old_map,
            new_map,
            rendered_map,
        )

# ── C-Extension Builder & Dynamic Loader ──────────────────────────────────
_NATIVE_RECONCILER_MODULE = None

def compile_reconciler_extension(output_path: Optional[str] = None) -> str:
    """Compile the native Nizam reconciler into a PEP 384 ABI3 shared library."""
    compiler_bin = _find_compiler()
    source_path = _find_reconciler_nz_source()

    if not output_path:
        cache_dir = os.path.join(os.path.dirname(source_path), "__pycache__", ".nizam_cache")
        with open(source_path, "rb") as f:
            src_hash = hashlib.sha256(f.read()).hexdigest()[:16]
        hash_dir = os.path.join(cache_dir, src_hash)
        os.makedirs(hash_dir, exist_ok=True)
        output_path = os.path.join(hash_dir, "nizam_reconciler.abi3.so")

    if os.path.isfile(output_path):
        return output_path

    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(compiler_bin)))
    lib_dir_flag = []
    if os.path.isdir(os.path.join(workspace_root, "mantiq")):
        lib_dir_flag = ["--lib-dir", os.path.join(workspace_root, "mantiq")]

    cmd = [compiler_bin, "build", source_path, "--target", "python-ext", "-o", output_path] + lib_dir_flag
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.isfile(output_path):
        raise RuntimeError(
            f"Failed to compile native reconciler extension:\nCommand: {' '.join(cmd)}\nSTDERR: {res.stderr}"
        )

    return output_path


def get_native_reconciler():
    """Retrieve or dynamically load the native C-extension reconciler module."""
    global _NATIVE_RECONCILER_MODULE
    if _NATIVE_RECONCILER_MODULE is not None:
        return _NATIVE_RECONCILER_MODULE

    # 1. Try normal import
    try:
        import nizam_reconciler
        _NATIVE_RECONCILER_MODULE = nizam_reconciler
        return _NATIVE_RECONCILER_MODULE
    except ImportError:
        pass

    # 2. Try compiling/locating cached shared library
    try:
        so_path = compile_reconciler_extension()
        loader = importlib.machinery.ExtensionFileLoader("nizam_reconciler", so_path)
        spec = importlib.util.spec_from_loader("nizam_reconciler", loader, origin=so_path)
        if spec:
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            _NATIVE_RECONCILER_MODULE = mod
            return _NATIVE_RECONCILER_MODULE
    except Exception:
        pass

    return None


def is_native_available() -> bool:
    """Check if the native C-extension is loaded or compilable."""
    return get_native_reconciler() is not None

# ── High-Level Reconciliation API ─────────────────────────────────────────
def _to_json_str(tree: Optional[Union[WidgetNode, Dict[str, Any], str]]) -> str:
    if tree is None:
        return "{}"
    if isinstance(tree, str):
        return tree
    if isinstance(tree, WidgetNode):
        return tree.to_json()
    if isinstance(tree, dict):
        return json.dumps(tree, separators=(",", ":"))
    raise TypeError(f"Unsupported tree type: {type(tree)}")


def _to_dict_obj(tree: Optional[Union[WidgetNode, Dict[str, Any], str]]) -> Optional[Dict[str, Any]]:
    if tree is None:
        return None
    if isinstance(tree, WidgetNode):
        return tree.to_dict()
    if isinstance(tree, dict):
        return tree
    if isinstance(tree, str):
        s = tree.strip()
        if not s or s == "{}":
            return None
        return json.loads(s)
    raise TypeError(f"Unsupported tree type: {type(tree)}")


def reconcile_json(
    old_tree_json: str,
    new_tree_json: str,
    use_native: bool = True,
) -> str:
    """Reconcile two Virtual DOM trees given as JSON strings and return a JSON string of patches."""
    if use_native:
        native_mod = get_native_reconciler()
        if native_mod is not None and hasattr(native_mod, "reconcile_json"):
            return native_mod.reconcile_json(old_tree_json, new_tree_json)

    # Pure Python fallback
    old_dict = _to_dict_obj(old_tree_json)
    new_dict = _to_dict_obj(new_tree_json)
    patches = PythonReconciler().reconcile(old_dict, new_dict)
    return json.dumps(patches, separators=(",", ":"))


def reconcile(
    old_tree: Optional[Union[WidgetNode, Dict[str, Any], str]],
    new_tree: Optional[Union[WidgetNode, Dict[str, Any], str]],
    use_native: bool = True,
) -> List[Dict[str, Any]]:
    """Reconcile two Virtual DOM trees and return a list of patch dictionaries."""
    old_json = _to_json_str(old_tree)
    new_json = _to_json_str(new_tree)

    patches_json = reconcile_json(old_json, new_json, use_native=use_native)
    return json.loads(patches_json)
