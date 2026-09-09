.DEFAULT_GOAL := help
.PHONY: help dev test lint fmt typecheck openapi bench mock up down db-url db-policies verify-security migrate render clean

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

up:  ## Start backing services (redis)
	docker compose -f docker-compose.dev.yml up -d

down:  ## Stop backing services
	docker compose -f docker-compose.dev.yml down

db-url:  ## Print the resolved database DSN with the password masked
	uv run python -c "from packages.database.session import settings; print(settings.safe_url)"

db-policies:  ## Apply extensions, RLS and storage buckets (Supabase-only concerns)
	supabase db push

verify-security:  ## Assert every application table has RLS and buckets are private
	uv run python scripts/maintenance/verify_security.py

migrate:  ## Apply database migrations
	uv run alembic upgrade head

render:  ## Render the simulated dataset (requires Blender)
	uv run python scripts/dataset/render_cases.py

clean:  ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
