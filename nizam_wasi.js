#!/usr/bin/env -S node --no-incremental-marking --stack-size=65536 --max-old-space-size=4096
// ── WASI Runtime Imports ──────────────────────────────────────────────
const { WASI } = require("wasi");
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

// ── Environment & Arguments Setup ──────────────────────────────────────
let wasmPath = process.env.NIZAM_WASM || path.resolve(__dirname, "../stage3/nizam.wasm");
let rawArgs = process.argv.slice(2);
if (rawArgs.length > 0 && rawArgs[0].endsWith(".wasm")) {
  wasmPath = path.resolve(rawArgs[0]);
  rawArgs = rawArgs.slice(1);
}
const args = [path.basename(wasmPath), ...rawArgs];

const wasi = new WASI({
  version: "preview1",
  args,
  env: process.env,
  preopens: {
    "/": "/",
    ".": "."
  }
});

const wasmBytes = fs.readFileSync(wasmPath);
const wasmModule = new WebAssembly.Module(wasmBytes);

// ── Host System Bridge ────────────────────────────────────────────────
let instance;
const importObject = wasi.getImportObject();
importObject.env = importObject.env || {};
importObject.env.host_system = (cmdPtr) => {
  const mem = new Uint8Array(instance.exports.memory.buffer);
  let end = cmdPtr;
  while (mem[end] !== 0) end++;
  const cmd = new TextDecoder().decode(mem.subarray(cmdPtr, end));
  try {
    execSync(cmd, { stdio: "inherit" });
    return 0;
  } catch (err) {
    return err.status || 1;
  }
};

// ── Execution ─────────────────────────────────────────────────────────
try {
  instance = new WebAssembly.Instance(wasmModule, importObject);
  const exitCode = wasi.start(instance);
  process.exit(exitCode || 0);
} catch (err) {
  console.error("WASI Execution Error:", err);
  process.exit(1);
}
