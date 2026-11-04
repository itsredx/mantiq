# Specification 0031: Standard System Interface (`std.sys`)

// ── Document Specification ──────────────────────────────────────────────────
// Number: 0031
// Title: Standard System Interface (`std.sys`)
// Status: Canonical Specification
// Supersedes: 0004-std-sys.md
// Related: 0002-std-process.md, 0010-std-path.md, 0011-type-system.md,
//          0013-memory-management.md, 0017-imports.md, 0026-ownership-and-borrowck.md
// Target Module: std/sys.nz

---

## 1. Scope & Objectives

This specification defines the syntax, type signatures, operational semantics, memory safety invariants, and multi-platform behavioral contracts for the **Nizam** standard system interface module: `std.sys`.

`std.sys` serves as the foundational operating system abstraction layer for both user applications and the self-hosted compiler toolchain (`nizam`, `mantiq`). It provides first-class support for:
1. **Host & Platform Introspection**: Querying the operating system name, processor architecture, word size, endianness, hardware concurrency, and virtual memory page size.
2. **Environment Variable Management**: Type-safe querying, mutation, iteration, and existence checks for process environment variables using `Option[T]` and `Result[T, E]`.
3. **Process Control & Arguments**: Accessing command-line arguments (`args()`), process identifiers (`pid()`, `ppid()`), and structured process termination (`exit()`, `abort()`).
4. **Injection-Safe Subprocess Spawning**: Launching child processes via an injection-safe `Command` builder pattern without `/bin/sh` shell escaping hazards, capturing status codes and standard streams.
5. **Streams & TTY Inspection**: Standard stream file descriptors, interactive terminal detection (`is_atty()`), and console dimension inspection.
6. **High-Resolution Clocks & Telemetry**: Monotonic nanosecond timers, epoch timestamps, thread sleeping, and resident memory usage.

---

## 2. Type Definitions & Data Structures

```nizam
// ── Terminal Dimensions ───────────────────────────────────────────────────────
struct TermSize:
    public var rows as u16
    public var cols as u16

// ── System Error Kinds ────────────────────────────────────────────────────────
enum SysErrorKind:
    NotFound            // File, binary, or environment variable not found (ENOENT)
    PermissionDenied    // Insufficient permissions to access resource (EACCES, EPERM)
    AlreadyExists       // Target entity already exists (EEXIST)
    Interrupted         // Interrupted by an OS signal (EINTR)
    InvalidInput        // Invalid argument or parameter (EINVAL)
    TimedOut            // Operation exceeded allocated deadline (ETIMEDOUT)
    OutOfMemory         // Operating system failed to allocate memory (ENOMEM)
    BrokenPipe          // Pipe writer closed or broken (EPIPE)
    Unknown             // Unclassified platform error

// ── Structured System Error ───────────────────────────────────────────────────
struct SysError:
    public var kind as SysErrorKind
    public var code as i32
    public var message as String

    public fn deinit(self as ptr[SysError]):
        (deref self).message.deinit()

// ── Standard Stream Redirection ───────────────────────────────────────────────
enum StdioConfig:
    Inherit             // Share standard streams with parent process
    Null                // Discard stream output (/dev/null or NUL)
    Piped               // Capture stream via anonymous OS pipe

// ── Subprocess Output ─────────────────────────────────────────────────────────
struct ProcessOutput:
    public var status as i32
    public var stdout as String
    public var stderr as String

    public fn deinit(self as ptr[ProcessOutput]):
        (deref self).stdout.deinit()
        (deref self).stderr.deinit()

// ── Injection-Safe Command Builder ────────────────────────────────────────────
struct Command:
    public var program as String
    public var args as List[String]
    public var env_vars as Dict[String, String]
    public var cwd as Option[String]
    public var stdin_cfg as StdioConfig
    public var stdout_cfg as StdioConfig
    public var stderr_cfg as StdioConfig
```

---

## 3. Module Interface & API Signatures

### 3.1 Host & Platform Introspection

```nizam
// ── Operating System ──────────────────────────────────────────────────────────
public fn os() as String
public fn is_windows() as bool
public fn is_linux() as bool
public fn is_macos() as bool
public fn is_wasi() as bool
public fn is_posix() as bool

// ── CPU Architecture ──────────────────────────────────────────────────────────
public fn arch() as String
public fn is_x86_64() as bool
public fn is_aarch64() as bool
public fn is_wasm32() as bool

// ── Word Size & Endianness ────────────────────────────────────────────────────
public fn pointer_size() as usize
public fn is_64bit() as bool
public fn is_32bit() as bool
public fn is_little_endian() as bool

// ── Memory & Core Topology ────────────────────────────────────────────────────
public fn page_size() as usize
public fn cpu_count() as usize
public fn hostname() as String
```

### 3.2 Environment Variable Management

```nizam
// ── Environment Getters ───────────────────────────────────────────────────────
public fn getenv(name as String) as Option[String]
public fn getenv_ref(name as ptr[String]) as Option[String]
public fn getenv_cstr(name as cstr) as Option[String]
public fn getenv_or(name as String, default_val as String) as String
public fn has_env(name as String) as bool
public fn has_env_ref(name as ptr[String]) as bool

// ── Environment Modifiers ─────────────────────────────────────────────────────
public fn setenv(name as String, value as String) as Result[Void, SysError]
public fn setenv_ref(name as ptr[String], value as ptr[String]) as Result[Void, SysError]
public fn unsetenv(name as String) as Result[Void, SysError]
public fn unsetenv_ref(name as ptr[String]) as Result[Void, SysError]

// ── Full Environment Block ────────────────────────────────────────────────────
public fn environ() as Dict[String, String]
```

### 3.3 Process Control & CLI Arguments

```nizam
// ── Command Line Arguments ────────────────────────────────────────────────────
public fn args() as List[String]
public fn argv0() as String

// ── Process Credentials & IDs ─────────────────────────────────────────────────
public fn pid() as i32
public fn ppid() as i32
public fn uid() as u32
public fn gid() as u32

// ── Process Lifecycle ─────────────────────────────────────────────────────────
public fn exit(code as i32) as never
public fn abort() as never
```

### 3.4 Process Execution & Command Builder

```nizam
// ── Construction ──────────────────────────────────────────────────────────────
public fn Command.new(program as String) as Command
public fn Command.new_ref(program as ptr[String]) as Command

// ── Builder Methods ───────────────────────────────────────────────────────────
public fn Command.arg(self as ptr[Command], val as String) as ptr[Command]
public fn Command.arg_ref(self as ptr[Command], val as ptr[String]) as ptr[Command]
public fn Command.args(self as ptr[Command], items as List[String]) as ptr[Command]
public fn Command.env(self as ptr[Command], key as String, val as String) as ptr[Command]
public fn Command.current_dir(self as ptr[Command], dir as String) as ptr[Command]
public fn Command.stdin(self as ptr[Command], cfg as StdioConfig) as ptr[Command]
public fn Command.stdout(self as ptr[Command], cfg as StdioConfig) as ptr[Command]
public fn Command.stderr(self as ptr[Command], cfg as StdioConfig) as ptr[Command]

// ── Execution Dispatch ────────────────────────────────────────────────────────
public fn Command.status(self as ptr[Command]) as Result[i32, SysError]
public fn Command.output(self as ptr[Command]) as Result[ProcessOutput, SysError]

// ── Quick Shell Execution ─────────────────────────────────────────────────────
public fn system(command as String) as i32
public fn system_ref(command as ptr[String]) as i32
```

### 3.5 Streams, Terminal & TTY

```nizam
// ── Standard File Descriptors ─────────────────────────────────────────────────
public const STDIN_FILENO as i32 = 0
public const STDOUT_FILENO as i32 = 1
public const STDERR_FILENO as i32 = 2

// ── TTY Queries ───────────────────────────────────────────────────────────────
public fn is_atty(fd as i32) as bool
public fn terminal_size() as Option[TermSize]
public fn terminal_columns() as u16
```

### 3.6 Clocks, Sleeping & Telemetry

```nizam
// ── High Resolution Timers ────────────────────────────────────────────────────
public fn now_monotonic_ns() as u64
public fn now_realtime_sec() as i64

// ── Sleep Primitives ──────────────────────────────────────────────────────────
public fn sleep_ms(ms as u64)
public fn sleep_ns(ns as u64)

// ── Memory Telemetry ──────────────────────────────────────────────────────────
public fn rss_bytes() as usize
```

---

## 4. Operational Semantics & Behavioral Invariants

### 4.1 Host Operating System & Architecture Detection
- `os()` returns an owned `String` representing the lowercase target operating system identifier:
  - `"linux"` for Linux targets.
  - `"macos"` for Darwin / macOS targets.
  - `"windows"` for Win32 / MSVC targets.
  - `"wasi"` for WebAssembly WASI targets.
  - `"freebsd"` for FreeBSD targets.
- The value is derived from target compilation triple flags at compile-time and backed by runtime `uname()` verification on POSIX systems.
- `arch()` returns the canonical processor architecture: `"x86_64"`, `"aarch64"`, `"arm"`, `"wasm32"`, `"riscv64"`.

### 4.2 The Unset vs Empty Environment Invariant
- If an environment variable is not defined in the host environment block, `getenv(name)` MUST return `Option.None`.
- If an environment variable is defined with an empty string value (e.g. `export FOO=""`), `getenv(name)` MUST return `Option.Some(String.make("" to cstr))`.
- This strictly resolves the legacy C runtime defect where `mantiq_sys_getenv` returned `""` for both cases.

### 4.3 Dual-Signature Ownership & Move Semantics
For every function `F(s as String)` that consumes a string:
1. `F` accepts `s` by value, taking ownership. The argument is freed upon completion of `F`.
2. `F_ref(s as ptr[String])` accepts a borrowed reference. `s` remains owned by the caller and its lifetime is unaffected.
3. Callers MUST NOT use `s` after passing it to the by-value variant (enforced statically by error `[E0401]` `UseAfterMove`).

### 4.4 Injection-Safe Child Process Execution
- Invoking `Command.status()` or `Command.output()` executes the program directly via `posix_spawnp` (POSIX) or `CreateProcessA` (Windows).
- Arguments registered via `.arg()` or `.args()` are passed as individual elements of the `argv` array without shell parsing. Whitespace, quotes, semicolons, and special characters inside argument strings are passed verbatim to the target program without command injection hazard.
- `system()` remains available for legacy code requiring shell command execution, but delegates internally to `/bin/sh -c` on POSIX and `cmd.exe /c` on Windows.

### 4.5 Process Termination Invariant
- Calling `exit(code)` flushes all standard I/O streams and immediately terminates the calling process with status `code`. It never returns to the caller (`never` return type).
- Calling `abort()` triggers an abnormal process abort (SIGABRT on POSIX, `RaiseFailFastException` on Windows), generating a core dump or crash report if enabled.

---

## 5. Usage Examples

```nizam
// ── Imports ───────────────────────────────────────────────────────────────────
import std.sys
from std.sys import Command, StdioConfig, os, is_windows, getenv_cstr

fn main() as i32:
    // 1. Host Architecture & Platform
    println(f"Host OS: {os()}")
    if is_windows():
        println("Running on Microsoft Windows")
    else:
        println("Running on POSIX compatible host")

    // 2. Querying Environment Variables
    let path_opt = getenv_cstr("PATH" to cstr)
    match path_opt:
        Some(path_val):
            println(f"System PATH length: {path_val.len}")
        None:
            println("PATH environment variable not set")

    // 3. Spawning Child Process Securely
    var cmd as Command = Command.new(String.make("git" to cstr))
    cmd.arg(String.make("status" to cstr))
    cmd.arg(String.make("--short" to cstr))
    
    let out_res = cmd.output()
    match out_res:
        Ok(out):
            println(f"Git status exit code: {out.status}")
            println(f"Git output:\n{out.stdout}")
        Err(err):
            println(f"Failed to execute git: {err.message}")

    // 4. Clean Process Exit
    std.sys.exit(0)
```

---

## 6. Diagnostic Codes & Errors

| Error Code | Identifier | Trigger Condition |
| :--- | :--- | :--- |
| `[E0104]` | `SymbolNotFound` | Attempting to import non-existent symbol from `std.sys` |
| `[E0401]` | `UseAfterMove` | Attempting to access `name` after passing by-value to `getenv(name)` |
| `[E0406]` | `AliasingViolation` | Attempting to mutably borrow a command while an immutable borrow is live |
| `[E0701]` | `ProcessSpawnFailed` | Failed to locate executable or allocate process handles during `Command.status()` |
| `[E0702]` | `EnvironmentError` | Failed to write to process environment block due to invalid name character (`=`) |

