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
    parser.add_argument("input", help="Path to input Python file (.py)")
    parser.add_argument("-o", "--output", help="Path to output Nizam file (.nz)")
    parser.add_argument("-p", "--print", action="store_true", help="Print transpiled code to stdout")
    parser.add_argument("-r", "--run", action="store_true", help="Execute the transpiled code via mantiq run")
    parser.add_argument("--mantiq-bin", default=None, help="Path to mantiq/nizam executable")

    args = parser.parse_args(argv)

    if not os.path.exists(args.input):
        sys.stderr.write(f"Error: Input file not found: {args.input}\n")
        return 1

    out_path = args.output
    if not out_path and not args.print:
        base, _ = os.path.splitext(args.input)
        out_path = f"{base}.nz"

    transpiler = Transpiler()
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
