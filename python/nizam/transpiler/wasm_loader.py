# ── Imports ─────────────────────────────────────────────────────────────
import os
from typing import Optional

# ── WebAssembly Loader & Container Generator ────────────────────────────
class WasmLoaderGenerator:
    """Generates lightweight browser HTML/JS container and WASI Preview 1 runner."""

    DEFAULT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{app_title}</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --surface-color: #1e293b;
            --text-color: #f8fafc;
            --accent-color: #38bdf8;
            --border-color: #334155;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 1.5rem;
        }}
        #app-root {{
            width: 100%;
            max-width: 800px;
            background-color: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
        }}
        #status-bar {{
            margin-top: 1rem;
            font-size: 0.85rem;
            color: #94a3b8;
            display: flex;
            justify-content: space-between;
        }}
        .badge {{
            background-color: rgba(56, 189, 248, 0.15);
            color: var(--accent-color);
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-weight: 500;
        }}
        #log-output {{
            margin-top: 1.5rem;
            width: 100%;
            max-width: 800px;
            background-color: #020617;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.8rem;
            color: #a5f3fc;
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>
    <div id="app-root">
        <h1>{app_title}</h1>
        <p style="margin-top: 0.5rem; color: #94a3b8;">Loading Nizam WebAssembly runtime...</p>
    </div>

    <div id="status-bar">
        <span>Target: <span class="badge">wasm32-wasi</span></span>
        <span id="load-time">Initializing...</span>
    </div>

    <div id="log-output"></div>

    <script src="{js_filename}"></script>
    <script>
        window.addEventListener("DOMContentLoaded", async () => {{
            const startTime = performance.now();
            const logEl = document.getElementById("log-output");
            const loadTimeEl = document.getElementById("load-time");

            function log(msg) {{
                if (logEl) {{
                    logEl.textContent += msg + "\\n";
                    logEl.scrollTop = logEl.scrollHeight;
                }}
                console.log(msg);
            }}

            try {{
                const runner = new NizamWasiRunner("{wasm_filename}", {{
                    stdout: log,
                    stderr: log,
                    domRoot: document.getElementById("app-root")
                }});

                await runner.start();
                const elapsed = (performance.now() - startTime).toFixed(1);
                loadTimeEl.textContent = `Cold startup: ${{elapsed}} ms`;
            }} catch (err) {{
                log(`[Error] Failed to initialize Nizam WASM application: ${{err}}`);
                loadTimeEl.textContent = "Initialization Failed";
            }}
        }});
    </script>
</body>
</html>
"""

    DEFAULT_JS_TEMPLATE = """// ── Nizam Standalone WebAssembly WASI Runner & Virtual DOM Bridge ────────
class NizamWasiRunner {
    constructor(wasmPath, options = {}) {
        this.wasmPath = wasmPath;
        this.options = options;
        this.stdout = options.stdout || console.log;
        this.stderr = options.stderr || console.error;
        this.domRoot = options.domRoot || document.getElementById("app-root");
        this.memory = null;
        this.instance = null;
        this.utf8Decoder = new TextDecoder("utf-8");
        this.utf8Encoder = new TextEncoder();
        this.outBuffer = "";
        if (typeof window !== "undefined") {
            window.__nizam_apply_patches = (patches) => this.applyDomPatches(patches);
        }
    }

    getImports() {
        const self = this;
        return {
            wasi_snapshot_preview1: {
                fd_write(fd, iovs_ptr, iovs_len, nwritten_ptr) {
                    const view = new DataView(self.memory.buffer);
                    let written = 0;
                    let text = "";

                    for (let i = 0; i < iovs_len; i++) {
                        const ptr = view.getUint32(iovs_ptr + i * 8, true);
                        const len = view.getUint32(iovs_ptr + i * 8 + 4, true);
                        const bytes = new Uint8Array(self.memory.buffer, ptr, len);
                        text += self.utf8Decoder.decode(bytes);
                        written += len;
                    }

                    view.setUint32(nwritten_ptr, written, true);

                    // Check for virtual DOM JSON patch payloads: [PATCHES: {...}]
                    if (text.includes("[PATCHES:")) {
                        const match = text.match(/\\[PATCHES:(.*?)\\]/s);
                        if (match && match[1]) {
                            try {
                                const patches = JSON.parse(match[1]);
                                self.applyDomPatches(patches);
                            } catch (e) {
                                self.stderr("[DOM Bridge Error] " + e);
                            }
                        }
                    }

                    if (fd === 1) {
                        self.stdout(text);
                    } else if (fd === 2) {
                        self.stderr(text);
                    }
                    return 0;
                },

                fd_read() { return 0; },
                fd_close() { return 0; },
                fd_seek() { return 0; },
                fd_fdstat_get(fd, stat_ptr) {
                    const view = new DataView(self.memory.buffer);
                    view.setUint8(stat_ptr, 2); // character device
                    view.setUint16(stat_ptr + 2, 0, true);
                    return 0;
                },

                clock_time_get(clockId, precision, time_ptr) {
                    const view = new DataView(self.memory.buffer);
                    const now = BigInt(Math.floor(performance.now() * 1e6));
                    view.setBigUint64(time_ptr, now, true);
                    return 0;
                },

                random_get(buf_ptr, buf_len) {
                    const buf = new Uint8Array(self.memory.buffer, buf_ptr, buf_len);
                    if (window.crypto && window.crypto.getRandomValues) {
                        window.crypto.getRandomValues(buf);
                    } else {
                        for (let i = 0; i < buf_len; i++) {
                            buf[i] = Math.floor(Math.random() * 256);
                        }
                    }
                    return 0;
                },

                proc_exit(code) {
                    self.stdout(`[Nizam WASI] Process exited with status code: ${code}`);
                    return 0;
                },

                environ_sizes_get(count_ptr, size_ptr) {
                    const view = new DataView(self.memory.buffer);
                    view.setUint32(count_ptr, 0, true);
                    view.setUint32(size_ptr, 0, true);
                    return 0;
                },

                environ_get() { return 0; },

                args_sizes_get(argc_ptr, argv_buf_size_ptr) {
                    const view = new DataView(self.memory.buffer);
                    view.setUint32(argc_ptr, 0, true);
                    view.setUint32(argv_buf_size_ptr, 0, true);
                    return 0;
                },

                args_get() { return 0; }
            },
            env: {
                mantiq_js_eval(str_ptr, str_len) {
                    const bytes = new Uint8Array(self.memory.buffer, str_ptr, str_len);
                    const js = self.utf8Decoder.decode(bytes);
                    try {
                        eval(js);
                    } catch (e) {
                        self.stderr("[Eval Error] " + e);
                    }
                    return 0;
                }
            }
        };
    }

    applyDomPatches(patches) {
        if (!Array.isArray(patches) || !this.domRoot) return;

        for (const patch of patches) {
            const { action, html_id, payload } = patch;
            const el = html_id ? document.getElementById(html_id) : null;

            switch (action) {
                case "replace_node":
                case "mount_tree":
                    if (this.domRoot) {
                        this.domRoot.innerHTML = payload || "";
                    }
                    break;
                case "update_text":
                    if (el) el.textContent = payload || "";
                    break;
                case "update_props":
                    if (el && payload) {
                        try {
                            const props = JSON.parse(payload);
                            for (const [k, v] of Object.entries(props)) {
                                if (k === "className") el.className = v;
                                else if (k === "style") el.style.cssText = v;
                                else el.setAttribute(k, v);
                            }
                        } catch (e) {}
                    }
                    break;
                case "remove_node":
                    if (el && el.parentNode) {
                        el.parentNode.removeChild(el);
                    }
                    break;
                default:
                    break;
            }
        }
    }

    async start() {
        const importObject = this.getImports();
        let wasmModule;

        if (typeof WebAssembly.instantiateStreaming === "function") {
            try {
                const response = await fetch(this.wasmPath);
                const result = await WebAssembly.instantiateStreaming(response, importObject);
                this.instance = result.instance;
            } catch (e) {
                const response = await fetch(this.wasmPath);
                const bytes = await response.arrayBuffer();
                const result = await WebAssembly.instantiate(bytes, importObject);
                this.instance = result.instance;
            }
        } else {
            const response = await fetch(this.wasmPath);
            const bytes = await response.arrayBuffer();
            const result = await WebAssembly.instantiate(bytes, importObject);
            this.instance = result.instance;
        }

        this.memory = this.instance.exports.memory;

        // Call WASI entrypoint
        if (typeof this.instance.exports._start === "function") {
            this.instance.exports._start();
        } else if (typeof this.instance.exports.main === "function") {
            this.instance.exports.main();
        }
        return this.instance;
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { NizamWasiRunner };
}
"""

    def __init__(self, output_dir: str, app_title: str = "Nizam Web Application"):
        self.output_dir = output_dir
        self.app_title = app_title

    def generate(self, wasm_filename: str = "app.wasm") -> dict:
        """Emits index.html and nizam_app.js in output_dir."""
        os.makedirs(self.output_dir, exist_ok=True)
        js_filename = "nizam_app.js"
        html_filename = "index.html"

        js_path = os.path.join(self.output_dir, js_filename)
        with open(js_path, "w", encoding="utf-8") as f:
            f.write(self.DEFAULT_JS_TEMPLATE.strip() + "\n")

        html_content = self.DEFAULT_HTML_TEMPLATE.format(
            app_title=self.app_title,
            wasm_filename=wasm_filename,
            js_filename=js_filename,
        )
        html_path = os.path.join(self.output_dir, html_filename)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content.strip() + "\n")

        return {
            "html": html_path,
            "js": js_path,
        }
