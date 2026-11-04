# Specification 0004: std.sys Module (Superseded)

> [!NOTE]
> **Superseded by [Specification 0031: Standard System Interface (std.sys)](0031-std-sys-system-interface.md)** and **[Decision 0049: std.sys Native Platform Abstraction & C-Runtime Elimination](../decisions/0049-std-sys-platform-abstraction-and-runtime-elimination.md)**.
> This early specification was based on the legacy C-runtime helpers. Refer to Specification 0031 for the complete, canonical API including dual-signature ownership, `Option[String]` environment queries, injection-safe subprocess execution (`Command`), terminal TTY detection, and high-resolution timing.

- Feature: Standard Platform Information & Environment APIs
- Syntax:
  ```python
  import std.sys
  
  # Operating system detection
  let name = os()
  
  # CPU architecture detection
  let machine = arch()
  
  # Get environment variable
  let path = getenv("PATH")
  
  # Set environment variable
  setenv("MY_VAR", "value")
  
  # Unset environment variable
  unsetenv("MY_VAR")
  ```
- Semantics:
  - `os()` returns an `AsciiStr` representing the operating system (e.g. `"linux"`, `"macos"`, `"windows"`).
  - `arch()` returns an `AsciiStr` representing the CPU architecture (e.g. `"x86_64"`, `"aarch64"`).
  - `getenv(name)` takes one `AsciiStr` parameter representing the variable name and returns the variable's value as an `AsciiStr`. If not found, returns an empty string `""`.
  - `setenv(name, value)` takes two `AsciiStr` parameters and updates or sets the environment variable to `value`. Returns `Void`.
  - `unsetenv(name)` takes one `AsciiStr` parameter and deletes the variable from the environment. Returns `Void`.
- Examples:
  ```python
  import std.sys
  import std.io
  
  fn main():
      print("OS: ")
      println(os())
      
      setenv("TEMP_ENV", "HELLO")
      print("Val: ")
      println(getenv("TEMP_ENV"))
      
      unsetenv("TEMP_ENV")
  ```
- Errors:
  - Calling functions with wrong arity or incorrect parameter types yields compile-time type mismatch errors.
