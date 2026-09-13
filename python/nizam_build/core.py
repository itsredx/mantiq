# ── Nizam Build Backend Core (PEP 517 / PEP 518) ────────────────────────
"""Core implementation of PEP 517 build backend for Nizam packages."""

import os
import re
import sys
import shutil
import base64
import tarfile
import zipfile
import hashlib
import sysconfig
import subprocess
from typing import Dict, List, Optional, Any

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

def _normalize_name(name: str) -> str:
    """Normalize a package name per PEP 503 / PEP 508."""
    return re.sub(r"[-_.]+", "_", name).lower()

def _find_nizam_compiler() -> str:
    """Locate the Nizam compiler executable."""
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
        cand3 = os.path.join(curr, "mantiq", "nizam")
        if os.path.isfile(cand3) and os.access(cand3, os.X_OK):
            return cand3
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent

    raise FileNotFoundError("Could not find Nizam compiler binary ('nizam'). Please set NIZAM_BIN.")

def _read_pyproject_toml() -> Dict[str, Any]:
    """Parse pyproject.toml in the current working directory."""
    if not os.path.isfile("pyproject.toml"):
        raise FileNotFoundError("pyproject.toml not found in current directory.")
    if tomllib is not None:
        with open("pyproject.toml", "rb") as f:
            return tomllib.load(f)
    # Simple line-by-line fallback parser for basic pyproject.toml if tomllib missing
    res: Dict[str, Any] = {"project": {}, "tool": {"nizam": {}}}
    current_sec = ""
    with open("pyproject.toml", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_sec = line[1:-1]
                continue
            if "=" in line:
                k, v = [p.strip() for p in line.split("=", 1)]
                v = v.strip('"').strip("'")
                if current_sec == "project":
                    res["project"][k] = v
                elif current_sec in ("tool.nizam", "tool.nizam.build"):
                    res["tool"]["nizam"][k] = v
    return res

def get_requires_for_build_wheel(config_settings: Optional[Dict[str, Any]] = None) -> List[str]:
    return []

def get_requires_for_build_sdist(config_settings: Optional[Dict[str, Any]] = None) -> List[str]:
    return []

def _generate_dist_info(dest_dir: str, name: str, version: str, summary: str) -> str:
    """Generate METADATA and WHEEL files inside .dist-info directory."""
    dist_info = os.path.join(dest_dir, f"{_normalize_name(name)}-{version}.dist-info")
    os.makedirs(dist_info, exist_ok=True)

    metadata_path = os.path.join(dist_info, "METADATA")
    with open(metadata_path, "w", encoding="utf-8") as f:
        f.write("Metadata-Version: 2.1\n")
        f.write(f"Name: {name}\n")
        f.write(f"Version: {version}\n")
        f.write(f"Summary: {summary or 'Compiled Nizam native extension'}\n")

    wheel_path = os.path.join(dist_info, "WHEEL")
    plat = sysconfig.get_platform().replace("-", "_").replace(".", "_")
    with open(wheel_path, "w", encoding="utf-8") as f:
        f.write("Wheel-Version: 1.0\n")
        f.write("Generator: nizam_build (0.1.0)\n")
        f.write("Root-Is-Purelib: false\n")
        f.write(f"Tag: cp38-abi3-{plat}\n")

    return dist_info

def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings: Optional[Dict[str, Any]] = None) -> str:
    pyproject = _read_pyproject_toml()
    project = pyproject.get("project", {})
    name = project.get("name", "nizam_module")
    version = str(project.get("version", "0.1.0"))
    summary = str(project.get("description", ""))
    _generate_dist_info(metadata_directory, name, version, summary)
    return f"{_normalize_name(name)}-{version}.dist-info"

def build_wheel(
    wheel_directory: str,
    config_settings: Optional[Dict[str, Any]] = None,
    metadata_directory: Optional[str] = None,
) -> str:
    """Compile Nizam sources and bundle into a standard PEP 427 wheel."""
    pyproject = _read_pyproject_toml()
    project = pyproject.get("project", {})
    name = project.get("name", "nizam_module")
    version = str(project.get("version", "0.1.0"))
    summary = str(project.get("description", ""))

    norm_name = _normalize_name(name)
    plat = sysconfig.get_platform().replace("-", "_").replace(".", "_")
    wheel_tag = f"cp38-abi3-{plat}"
    wheel_filename = f"{norm_name}-{version}-{wheel_tag}.whl"
    wheel_path = os.path.join(wheel_directory, wheel_filename)

    tool_nizam = pyproject.get("tool", {}).get("nizam", {})
    sources: List[str] = tool_nizam.get("sources", [])

    if not sources:
        # Search for .nz or .mq in src/ or current directory
        search_dirs = ["src", "."]
        for sdir in search_dirs:
            if os.path.isdir(sdir):
                for f in os.listdir(sdir):
                    if (f.endswith(".nz") or f.endswith(".mq")) and not f.startswith("test_"):
                        sources.append(os.path.join(sdir, f))
                if sources:
                    break

    if not sources:
        raise ValueError("No Nizam sources found to compile. Specify 'sources' under [tool.nizam] in pyproject.toml.")

    compiler_bin = _find_nizam_compiler()
    build_temp = os.path.join(".nizam_build_tmp")
    os.makedirs(build_temp, exist_ok=True)

    workspace_root = os.path.dirname(os.path.dirname(compiler_bin))
    lib_dir_flag = []
    if os.path.isdir(os.path.join(workspace_root, "mantiq")):
        lib_dir_flag = ["--lib-dir", os.path.join(workspace_root, "mantiq")]
    elif os.path.isdir(os.path.join(os.path.dirname(compiler_bin), "mantiq")):
        lib_dir_flag = ["--lib-dir", os.path.join(os.path.dirname(compiler_bin), "mantiq")]

    compiled_artifacts: List[tuple[str, str]] = []  # (source_file, archive_arcname)

    try:
        for src in sources:
            src_path = os.path.abspath(src)
            src_leaf = os.path.splitext(os.path.basename(src_path))[0]
            out_so = os.path.join(build_temp, f"{src_leaf}.abi3.so")
            out_pyi = os.path.join(build_temp, f"{src_leaf}.pyi")

            cmd = [compiler_bin, "build", src_path, "--target", "python-ext", "-o", out_so] + lib_dir_flag
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not os.path.isfile(out_so):
                raise RuntimeError(
                    f"Nizam build failed for '{src}':\nCommand: {' '.join(cmd)}\n{res.stdout}\n{res.stderr}"
                )

            compiled_artifacts.append((out_so, f"{src_leaf}.abi3.so"))
            if os.path.isfile(out_pyi):
                compiled_artifacts.append((out_pyi, f"{src_leaf}.pyi"))

        # Create dist-info
        dist_info_dir = _generate_dist_info(build_temp, name, version, summary)
        dist_info_name = os.path.basename(dist_info_dir)

        # Assemble Wheel ZIP archive
        os.makedirs(wheel_directory, exist_ok=True)
        record_rows: List[str] = []

        with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as whl:
            # 1. Add compiled extensions & type stubs
            for local_path, arc_name in compiled_artifacts:
                whl.write(local_path, arcname=arc_name)
                with open(local_path, "rb") as f:
                    data = f.read()
                h = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("latin1").rstrip("=")
                record_rows.append(f"{arc_name},sha256={h},{len(data)}")

            # 2. Add dist-info files (except RECORD)
            for f_name in sorted(os.listdir(dist_info_dir)):
                if f_name == "RECORD":
                    continue
                f_path = os.path.join(dist_info_dir, f_name)
                arc_name = f"{dist_info_name}/{f_name}"
                whl.write(f_path, arcname=arc_name)
                with open(f_path, "rb") as f:
                    data = f.read()
                h = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode("latin1").rstrip("=")
                record_rows.append(f"{arc_name},sha256={h},{len(data)}")

            # 3. Add RECORD
            record_arc = f"{dist_info_name}/RECORD"
            record_rows.append(f"{record_arc},,")
            whl.writestr(record_arc, "\n".join(record_rows) + "\n")

    finally:
        shutil.rmtree(build_temp, ignore_errors=True)

    return wheel_filename

def build_sdist(sdist_directory: str, config_settings: Optional[Dict[str, Any]] = None) -> str:
    """Bundle the project into a source distribution tarball (.tar.gz)."""
    pyproject = _read_pyproject_toml()
    project = pyproject.get("project", {})
    name = project.get("name", "nizam_module")
    version = str(project.get("version", "0.1.0"))
    norm_name = _normalize_name(name)

    tar_filename = f"{norm_name}-{version}.tar.gz"
    tar_path = os.path.join(sdist_directory, tar_filename)
    os.makedirs(sdist_directory, exist_ok=True)

    root_prefix = f"{norm_name}-{version}"

    with tarfile.open(tar_path, "w:gz") as tar:
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("build", "dist", "__pycache__")]
            for f in files:
                if f.startswith(".") or f.endswith((".so", ".o", ".ll", ".wasm", ".whl", ".tar.gz")):
                    continue
                file_path = os.path.join(root, f)
                rel_path = os.path.relpath(file_path, ".")
                arc_name = os.path.join(root_prefix, rel_path)
                tar.add(file_path, arcname=arc_name)

    return tar_filename
