# ── Imports ────────────────────────────────────────────────────────────
import sys
import os
import argparse
import subprocess
from . import Transpiler

# ── CLI Implementation ────────────────────────────────────────────────
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="nizam-transpiler",
        description="Transpile Python source code into native Nizam (.nz) code."
    )
    parser.add_argument("input", nargs="?", default=None, help="Path to input Python file (.py)")
    parser.add_argument("-o", "--output", help="Path to output Nizam file (.nz) or .so extension")
    parser.add_argument("-p", "--print", action="store_true", help="Print transpiled code to stdout")
    parser.add_argument("-r", "--run", action="store_true", help="Execute the transpiled code via mantiq run")
    parser.add_argument("--mantiq-bin", default=None, help="Path to mantiq/nizam executable")
    parser.add_argument("--foreign-mode", choices=["extern", "import", "auto"], default="extern", help="Foreign module interop mode (extern, import, auto)")
    parser.add_argument("--workspace-root", default=None, help="Root directory for local module resolution")
    parser.add_argument("--build", action="store_true", help="Compile project into a standalone native or WebAssembly binary")
    parser.add_argument("--target", choices=["native", "wasm", "wasm32-wasi"], default="native", help="Compilation target: native (default) or wasm/wasm32-wasi")
    parser.add_argument("--release", action="store_true", help="Release mode: strip debug symbols and apply optimizations")
    parser.add_argument("--web-loader", action="store_true", help="Generate index.html and nizam_app.js container when targeting WebAssembly")
    parser.add_argument("--entry", default=None, help="Explicit entrypoint Python file when compiling a multi-file project")
    parser.add_argument("--build-reconciler", action="store_true", help="Compile native UI reconciler C-extension (.abi3.so)")

    args = parser.parse_args(argv)

    if args.build_reconciler:
        from ..reconciler import compile_reconciler_extension
        try:
            so_path = compile_reconciler_extension(args.output)
            print(f"✔ Native reconciler compiled successfully: {so_path}")
            return 0
        except Exception as e:
            sys.stderr.write(f"Reconciler compilation error: {e}\n")
            return 1

    if args.build:
        from .builder import ProjectBuilder
        input_path = args.input or os.getcwd()
        try:
            builder = ProjectBuilder(
                source_path=input_path,
                output_path=args.output,
                target=args.target,
                release=args.release,
                web_loader=args.web_loader,
                entrypoint=args.entry,
                foreign_mode=args.foreign_mode,
                workspace_root=args.workspace_root,
                mantiq_bin=args.mantiq_bin,
            )
            result = builder.build()
            print(f"✔ Build successful [{result['target']}]!")
            print(f"  Entrypoint: {result['entrypoint']}")
            print(f"  Transpiled: {result['transpiled_count']} module(s)")
            print(f"  Binary:     {result['output_path']} ({result['binary_size']} bytes)")
            if result.get("loader_files"):
                print(f"  Web Loader: {result['loader_files']['html']}, {result['loader_files']['js']}")
            return 0
        except Exception as e:
            sys.stderr.write(f"Build error: {e}\n")
            return 1

    if not args.input:
        parser.print_help(sys.stderr)
        return 1

    if not os.path.exists(args.input):
        sys.stderr.write(f"Error: Input file not found: {args.input}\n")
        return 1

    out_path = args.output
    if not out_path and not args.print:
        base, _ = os.path.splitext(args.input)
        out_path = f"{base}.nz"

    transpiler = Transpiler(foreign_mode=args.foreign_mode, workspace_root=args.workspace_root)
    try:
        transpiled = transpiler.transpile_file(args.input, out_path)
    except Exception as e:
        sys.stderr.write(f"Transpilation error: {e}\n")
        return 1

    if args.print or not out_path:
        print(transpiled)

    if out_path and not args.print:
        print(f"✔ Successfully transpiled {args.input} -> {out_path}")

    if args.run:
        # Locate mantiq / nizam compiler
        compiler_bin = args.mantiq_bin
        if not compiler_bin:
            candidates = [
                "./stage3/mantiq",
                "./mantiq/nizam",
                "./stage3/nizam",
                os.path.expanduser("~/.local/bin/mantiq"),
                os.path.expanduser("~/.local/bin/nizam"),
                "/usr/local/bin/mantiq",
            ]
            for cand in candidates:
                if os.path.exists(cand) and os.access(cand, os.X_OK):
                    compiler_bin = cand
                    break

        if not compiler_bin:
            sys.stderr.write("Error: Could not locate mantiq or nizam binary to run.\n")
            return 1

        run_file = out_path
        if not run_file:
            run_file = "/tmp/__transpiled_temp.nz"
            with open(run_file, "w", encoding="utf-8") as f:
                f.write(transpiled)

        print(f"── Running via {compiler_bin} run {run_file} ─────────────────")
        res = subprocess.run([compiler_bin, "run", run_file])
        return res.returncode

    return 0

if __name__ == "__main__":
    sys.exit(main())
