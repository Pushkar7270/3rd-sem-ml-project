.DEFAULT_GOAL := help

.PHONY: help setup install data train serve docs test lint format frontend-install frontend-build frontend-dev clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: install data ## Install dependencies and download the dataset

install: ## Create the environment and install dependencies
	uv sync

data: ## Download the IBM Telco Customer Churn dataset
	uv run python scripts/download_data.py

train: ## Train all models, explain, score customers and write reports
	uv run churn-train

serve: ## Start the FastAPI server on port 8000 (dashboard at /app/)
	uv run churn-serve

docs: ## Generate the Word project documentation and Claude PPT prompt
	uv run python scripts/generate_project_docs.py

frontend-install: ## Install React frontend dependencies (requires Node)
	cd frontend && npm install

frontend-build: ## Build the React dashboard into frontend/dist
	cd frontend && npm run build

frontend-dev: ## Run the Vite dev server on :5173 (proxies API to :8000)
	cd frontend && npm run dev

test: ## Run the test suite
	uv run pytest -q

lint: ## Run the linter
	uv run ruff check src tests scripts

format: ## Format the codebase
	uv run ruff format src tests scripts
	uv run ruff check src tests scripts --fix

clean: ## Remove generated artifacts and caches
	rm -rf artifacts reports data/processed .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
