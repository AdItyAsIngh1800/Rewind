.DEFAULT_GOAL := help
.PHONY: help dev test lint fmt typecheck openapi bench mock migrate render clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dev:  ## Create the environment from the lockfile
	uv sync --all-extras

test:  ## Run the test suite
	uv run pytest -q

lint:  ## Lint and format check
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## Auto-format
	uv run ruff format .
	uv run ruff check --fix .

typecheck:  ## Static type check
	uv run mypy packages services apps/api apps/worker

openapi:  ## Regenerate the frozen API contract
	uv run python scripts/export_openapi.py

bench:  ## Run the evaluation harness and emit a benchmark report
	uv run python scripts/evaluation/run_benchmark.py

mock:  ## Serve golden fixtures at the real API endpoints
	uv run uvicorn scripts.mock_api:app --reload --port 8000

migrate:  ## Apply database migrations
	uv run alembic upgrade head

render:  ## Render the simulated dataset (requires Blender)
	uv run python scripts/dataset/render_cases.py

clean:  ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
