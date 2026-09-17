# heatmatch — top-level targets (spec §1)
# Phases are independent; `check` runs everything CI runs.

.PHONY: help ingest core-test wasm web-dev web-build check fmt clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

ingest:  ## Rebuild data/ from upstream sources (hits the network)
	cd ingest && PYTHONPATH=src uv run python -m ingest run --region all

core-test:  ## cargo fmt check + clippy + tests for the Rust workspace
	cd core && cargo fmt --all -- --check
	cd core && cargo clippy --workspace --all-targets -- -D warnings
	cd core && cargo test --workspace

wasm:  ## Build the wasm package into web/src/wasm (not committed)
	wasm-pack build core/heatmatch-wasm --target bundler --release --out-dir ../../web/src/wasm

wasm-node:  ## Build a nodejs-target package for the smoke test
	wasm-pack build core/heatmatch-wasm --target nodejs --release --out-dir pkg-node

wasm-test: wasm-node  ## Build the node package and run the smoke test
	node core/heatmatch-wasm/tests/smoke.mjs

web-dev: wasm  ## Next.js dev server
	cd web && pnpm install && pnpm dev

web-build: wasm  ## Static export to web/out
	cd web && pnpm install && pnpm build

check: core-test wasm-test  ## Everything CI runs
	cd ingest && uv sync --locked
	cd ingest && uv run ruff check .
	cd ingest && uv run pytest
	cd web && pnpm lint && pnpm typecheck

fmt:  ## Format Rust and TS in place
	cd core && cargo fmt --all
	cd web && pnpm format

clean:
	rm -rf core/target web/.next web/out web/src/wasm web/public/data core/heatmatch-wasm/pkg-node
