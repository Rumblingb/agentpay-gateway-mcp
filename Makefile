# AgentPay Gateway MCP — Build & Run Commands

.PHONY: help install dev db-test test lint build docker-run docker-build clean

help:
	@echo "AgentPay Gateway MCP — Available Commands:"
	@echo ""
	@echo "  install     Install Python dependencies"
	@echo "  dev         Run in development mode (with sample backend mocks)"
	@echo "  db-test     Bootstrap and test database only"
	@echo "  test        Run all tests"
	@echo "  lint        Check code style"
	@echo "  build       Build Docker image"
	@echo "  docker-run  Run via Docker Compose"
	@echo "  docker-build Build all Docker images"
	@echo "  clean       Remove build artifacts"
	@echo ""

install:
	pip install -r requirements.txt
	pip install pytest pytest-asyncio httpx

dev:
	export LOCAL_BACKENDS=1 && python3 server.py --port 8000

db-test:
	python3 server.py --db-only

test:
	python3 -m pytest tests/ -v --tb=short

test-cov:
	python3 -m pytest tests/ -v --tb=short --cov=server --cov-report=term-missing

lint:
	python3 -m flake8 server.py --max-line-length=120 --ignore=E501,W503 || true
	python3 -m mypy server.py --ignore-missing-imports || true

build:
	docker build -t agentpay/gateway-mcp:latest .

docker-run:
	docker-compose up -d

docker-build:
	docker-compose build

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true