# TODO

- [ ] Create and publish a Homebrew tap/formula for `raiplaysound-cli` so the tool can be installed publicly with `brew install`.

## Propositions

- [ ] **Cross-platform rewrite for distributable CLI runtime**
  - Assessment: Replacing the Bash implementation with a cross-platform runtime (Python or another compiled CLI-friendly language) would remove shell portability constraints and enable first-class support for Linux, macOS, and Windows packaging.
  - Actions:
  - [ ] Define selection criteria and choose target runtime (Python, Go, or Rust) based on packaging, startup cost, maintenance effort, and dependency model.
  - [ ] Define a compatibility contract that preserves current CLI UX (`list`/`download`, options, config keys, and archive behavior).
  - [ ] Design a platform-agnostic architecture for downloader orchestration, metadata/cache handling, and progress rendering with graceful non-TTY fallback.
  - [ ] Implement a minimally complete prototype that supports the `download musicalbox` flow with archive idempotency and existing naming behavior.
  - [ ] Add automated cross-platform CI validation (Linux, macOS, Windows) with smoke tests for list/download and config loading.
  - [ ] Implement distribution pipelines (PyPI + `pipx` if Python, or static binaries + release assets if Go/Rust) and update installation docs.
