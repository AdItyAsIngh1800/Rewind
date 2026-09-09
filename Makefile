.DEFAULT_GOAL := help
.PHONY: help dev test lint fmt typecheck openapi bench mock up down db-url db-policies verify-security verify-contrast tokens migrate scene validate-cases gt render render-fg render-watch render-status render-stop validate-gt manifest clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dev:  ## Create the environment from the lockfile
	uv sync --all-extras

test:  ## Run the test suite
	uv run pytest -q

lint:  ## Lint, format and docstring/annotation check
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages services apps/api apps/worker

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

verify-contrast:  ## Assert colour tokens pass WCAG and colour-vision separation
	uv run python scripts/maintenance/verify_contrast.py

tokens:  ## Regenerate tokens.css and the evidence swatch page
	uv run python scripts/maintenance/generate_tokens.py
	uv run python scripts/maintenance/generate_swatches.py

migrate:  ## Apply database migrations
	uv run alembic upgrade head

scene:  ## Build the Blender warehouse scene from ml/configs/scene_v1.json
	blender --background --python scripts/dataset/build_scene.py -- --out data/scene/warehouse.blend

render:  ## Render any case that has no video yet, logging to artifacts/render.log
	@mkdir -p artifacts
	@echo "Rendering in the background. Watch with: make render-watch"
	@nohup blender --background data/scene/warehouse.blend \
	  --python scripts/dataset/render_cases.py -- --case all --skip-existing \
	  > artifacts/render.log 2>&1 &
	@sleep 2 && echo "started, pid $$(pgrep -f render_cases.py | head -1)"

render-fg:  ## Same, but in the foreground so you can watch it directly
	blender --background data/scene/warehouse.blend --python scripts/dataset/render_cases.py -- --case all --skip-existing

render-watch:  ## Follow the render log
	tail -f artifacts/render.log

render-status:  ## How many cases are rendered, and what is running
	@for c in data/samples/case_*; do \
	   n=$$(ls $$c/*.mp4 2>/dev/null | wc -l | tr -d ' '); \
	   printf "  %s  %s/3 cameras\n" "$$(basename $$c)" "$$n"; \
	 done
	@pgrep -f render_cases.py >/dev/null 2>&1 \
	   && echo "  render is RUNNING (pid $$(pgrep -f render_cases.py | head -1))" \
	   || echo "  no render running"

render-stop:  ## Stop a background render
	@pkill -f render_cases.py && echo "stopped" || echo "nothing running"

validate-cases:  ## Lint case waypoints against the scene geometry, before rendering
	uv run python scripts/dataset/validate_cases.py

gt:  ## Export ground truth for every case without rendering video (about 40s)
	blender --background data/scene/warehouse.blend --python scripts/dataset/render_cases.py -- --case all --gt-only

validate-gt:  ## Validate rendered ground truth against the frozen contracts
	uv run python scripts/dataset/validate_ground_truth.py data/samples/case_*

manifest:  ## Write the dataset manifest with checksums
	uv run python scripts/dataset/make_manifest.py --dataset-version v1

clean:  ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
