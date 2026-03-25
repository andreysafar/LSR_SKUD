.PHONY: help install test test-integration test-unit benchmark lint format clean

help:  ## Show this help message
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install:  ## Install dependencies
	uv sync --all-extras

install-dev:  ## Install development dependencies
	uv sync --all-extras --dev

test:  ## Run all tests
	uv run pytest tests/ -v

test-unit:  ## Run unit tests only
	uv run pytest tests/unit/ -v -m "not slow"

test-integration:  ## Run integration tests
	uv run pytest tests/integration/ -v -m "not gpu"

test-gpu:  ## Run GPU tests (requires GPU)
	uv run pytest tests/ -v -m "gpu"

test-coverage:  ## Run tests with coverage report
	uv run pytest tests/ --cov=. --cov-report=html --cov-report=term

benchmark:  ## Run performance benchmarks
	uv run python benchmarks/anpr_performance.py

benchmark-full:  ## Run comprehensive benchmarks
	uv run python -c "from benchmarks.anpr_performance import ANPRBenchmark; b = ANPRBenchmark(); suite = b.run_comprehensive_benchmark(100, 3); b.print_results(suite)"

lint:  ## Run code linting
	uv run flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	uv run flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

format:  ## Format code with black and isort
	uv run black .
	uv run isort .

type-check:  ## Run type checking with mypy
	uv run mypy . --ignore-missing-imports

clean:  ## Clean up temporary files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf benchmark_results_*.json

docker-build:  ## Build Docker image
	docker build -t lsr-skud:latest .

docker-run:  ## Run Docker container
	docker run -p 8501:8501 lsr-skud:latest

quality:  ## Run all quality checks
	$(MAKE) format
	$(MAKE) lint
	$(MAKE) type-check
	$(MAKE) test

# Development workflow
dev-setup:  ## Set up development environment
	$(MAKE) install-dev
	$(MAKE) format
	$(MAKE) lint

# CI workflow  
ci:  ## Run CI pipeline
	$(MAKE) install
	$(MAKE) lint
	$(MAKE) test-coverage
	$(MAKE) benchmark