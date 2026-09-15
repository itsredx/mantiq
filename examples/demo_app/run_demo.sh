#!/usr/bin/env bash
# ── Nizam & Mantiq Standalone AOT Demo Runner ──────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export PYTHONPATH="$WORKSPACE_ROOT/mantiq/python:$PYTHONPATH"

MODE="${1:---all}"

echo "================================================================"
echo "  🚀 Nizam & Mantiq AOT Python Transpilation & Deployment Demo"
echo "================================================================"
echo "Workspace Root: $WORKSPACE_ROOT"
echo "Project Dir:    $SCRIPT_DIR"
echo ""

build_native() {
    echo "── [1/2] Building Standalone Native Binary ──"
    python3 -m nizam.transpiler \
        --build "$SCRIPT_DIR" \
        -o "$SCRIPT_DIR/dist/demo_native" \
        --target native \
        --release \
        --workspace "$WORKSPACE_ROOT"
    
    echo ""
    echo "✔ Native build complete: $SCRIPT_DIR/dist/demo_native"
    echo "── Executing Native Binary (Zero Python Runtime) ──"
    "$SCRIPT_DIR/dist/demo_native"
    echo ""
}

build_wasm() {
    echo "── [2/2] Building WebAssembly (WASI) Bundle & Web Loader ──"
    python3 -m nizam.transpiler \
        --build "$SCRIPT_DIR" \
        -o "$SCRIPT_DIR/dist/demo_wasm.wasm" \
        --target wasm \
        --web-loader \
        --workspace "$WORKSPACE_ROOT"

    echo ""
    echo "✔ WebAssembly build complete: $SCRIPT_DIR/dist/demo_wasm.wasm"
    echo "── Executing WASM Module via Node.js WASI Preview 1 Runner ──"
    if [ -f "$WORKSPACE_ROOT/nizam_wasi.js" ] && command -v node >/dev/null 2>&1; then
        node "$WORKSPACE_ROOT/nizam_wasi.js" "$SCRIPT_DIR/dist/demo_wasm.wasm"
    fi
    echo ""
    echo "✔ Browser Web Loader generated at:"
    echo "    $SCRIPT_DIR/dist/index.html"
    echo "    $SCRIPT_DIR/dist/nizam_app.js"
    echo ""
    echo "To view in browser, run:"
    echo "    python3 -m http.server 8080 --directory $SCRIPT_DIR/dist"
    echo "    and open http://localhost:8080"
    echo ""
}

case "$MODE" in
    --native)
        build_native
        ;;
    --wasm)
        build_wasm
        ;;
    --web)
        build_wasm
        echo "Starting local HTTP server on http://localhost:8080 (Ctrl+C to stop)..."
        python3 -m http.server 8080 --directory "$SCRIPT_DIR/dist"
        ;;
    --all|*)
        build_native
        build_wasm
        echo "================================================================"
        echo "  🎉 All targets built and executed successfully!"
        echo "================================================================"
        ;;
esac
