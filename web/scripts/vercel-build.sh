#!/usr/bin/env bash
# Vercel build. The image has Node but no Rust, and the engine is Rust
# compiled to wasm, so the toolchain is installed first. rustup is ~10 s;
# the wasm-pack installer fetches a prebuilt binary rather than compiling
# it. The crate itself builds from scratch each deploy (the cargo target
# dir is not cached) — a few minutes, fine for a static site.
set -euo pipefail

if ! command -v cargo >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --profile minimal --target wasm32-unknown-unknown
fi
# shellcheck disable=SC1091
source "$HOME/.cargo/env"
rustup target add wasm32-unknown-unknown

if ! command -v wasm-pack >/dev/null 2>&1; then
  curl -sSf https://rustwasm.github.io/wasm-pack/installer/init.sh | sh
fi

# prebuild runs `wasm` and `copy-data`, then next build exports to out/.
pnpm build
