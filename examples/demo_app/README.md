# 🚀 Nizam & Mantiq AOT Python Transpiler Demo Application

This is a multi-module Python application compiled Ahead-of-Time (AOT) to **Standalone Native Binary** (Linux x86_64) and **WebAssembly** (`wasm32-wasi`) without Python interpreter or Pyodide dependencies.

---

## 📂 Project Architecture

```
examples/demo_app/
├── app.py                 # Main application entrypoint
├── engine/
│   ├── math_ops.py        # Recursive math functions, loops, and prime checks
│   └── models.py          # Class & struct domain models (Counter)
├── run_demo.sh            # Automated compilation and execution script
├── dist/                  # Output binaries and browser loader
│   ├── demo_native        # Standalone native Linux ELF binary (110 KB)
│   ├── demo_wasm.wasm     # Standalone WebAssembly module (760 KB)
│   ├── index.html         # Zero-Pyodide browser container (<50ms boot)
│   └── nizam_app.js       # Pure JavaScript WASI Preview 1 runner + DOM bridge
└── README.md
```

---

## ⚡ Quick Start

### 1. Build and Run All Targets (Native + WASM)
```bash
./examples/demo_app/run_demo.sh
```

### 2. Run Standalone Native Binary Directly
```bash
./examples/demo_app/run_demo.sh --native
# Or directly invoke the compiled binary:
./examples/demo_app/dist/demo_native
```

### 3. Run Standalone WebAssembly via Node.js WASI
```bash
./examples/demo_app/run_demo.sh --wasm
# Or directly run with the canonical WASI runner:
node nizam_wasi.js examples/demo_app/dist/demo_wasm.wasm
```

### 4. Run Live in Browser
```bash
./examples/demo_app/run_demo.sh --web
```
Or start a local web server:
```bash
python3 -m http.server 8080 --directory examples/demo_app/dist
```
Then navigate to **`http://localhost:8080`** in any web browser to see the live WebAssembly app render virtual DOM patches with sub-50ms cold startup time!

---

## 🛠 Manual CLI Compilation Commands

### Compile Native Executable (Release Mode):
```bash
python3 -m nizam.transpiler \
    --build examples/demo_app \
    -o examples/demo_app/dist/demo_native \
    --target native \
    --release
```

### Compile WebAssembly & Browser Loader:
```bash
python3 -m nizam.transpiler \
    --build examples/demo_app \
    -o examples/demo_app/dist/demo_wasm.wasm \
    --target wasm \
    --web-loader
```
