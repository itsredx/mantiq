# Mantiq & Nizam Self-Hosted Compiler

The self-hosted compiler suite for the **Mantiq** and **Nizam** programming languages. Unlike the bootstrap compiler written in Zig ([mantiqz](file:///mantiqz)), this version of the compiler is written in **Nizam** itself.

## Languages Overview

- **Nizam**: A strict, static, safe systems programming language designed for predictability and performance. Features manual memory management, no implicit allocations, and an ownership/borrowing model. Nizam files end with `.nz`.
- **Mantiq**: A gradual, dynamically-typed script counterpart that prioritizes ease-of-use and quick iterations. Mantiq files end with `.mq`.

---

## Repository Structure

- [src/](file:///mantiq/src) — The self-hosted compiler codebase written in Nizam.
- [std/](file:///mantiq/std) — The standard library code for Mantiq and Nizam (collections, math, path, string, text, etc.).
- [tree-sitter-mantiq/](file:///mantiq/tree-sitter-mantiq) — Tree-sitter parser definitions.

---

## Bootstrapping the Compiler

Since this compiler is written in Nizam, you need a pre-existing compiler to compile it. This process is called bootstrapping.

### Step 1: Build the Zig Bootstrap Compiler
If you haven't already, build the Zig-based compiler inside the `mantiqz` directory:

```bash
cd ../mantiqz/mantiq-compiler
zig build
```
This produces the bootstrap compiler executable at `../mantiqz/mantiq-compiler/zig-out/bin/nizam`.

### Step 2: Compile the Self-Hosted Compiler (Stage 1)
Use the bootstrap compiler to compile the self-hosted compiler source code:

```bash
../mantiqz/mantiq-compiler/zig-out/bin/nizam build src/main.nz -o ./nizam
```
This produces a `nizam` binary in the current directory.

### Step 3: Self-Host (Stage 2)
Verify that the compiled Nizam compiler can compile itself:

```bash
./nizam build src/main.nz -o ./nizam-selfhosted
```
If the compilation succeeds, `./nizam-selfhosted` is a fully self-hosted compiler!

---

## Portability & Dependencies
The generated compiler binaries require:
1. `zig` installed and in your `PATH` (for the C backend invocation).
2. `libmimalloc` installed on the host system.
