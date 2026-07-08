SHELL := /bin/bash

.PHONY: help install install-local setup setup-local dev-local check-local-services local api frontend start stop restart logs clean test

help:
	@echo "Post-Harvest Knowledge Scraper - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install Python dependencies"
	@echo "  make install-local    Install Python and frontend dependencies"
	@echo "  make setup            Full setup (install + init DB)"
	@echo "  make setup-local      Non-Docker setup (install deps + init DB)"
	@echo "  make dev-local        Non-Docker setup + run API/frontend"
	@echo ""
	@echo "Services:"
	@echo "  make local            Run API and frontend outside Docker"
	@echo "  make api              Run FastAPI outside Docker"
	@echo "  make frontend         Run Vite frontend outside Docker"
	@echo "  make start            Start all Docker services"
	@echo "  make stop             Stop all Docker services"
	@echo "  make restart          Restart all Docker services"
	@echo "  make logs             View Docker logs"
	@echo ""
	@echo "Database:"
	@echo "  make init-db          Initialize database"
	@echo "  make db-shell         Open PostgreSQL shell"
	@echo ""
	@echo "Development:"
	@echo "  make dashboard        Start Streamlit dashboard"
	@echo "  make crawl-naro       Run NARO crawl"
	@echo "  make crawl-all        Run all site crawls"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean            Clean up generated files"
	@echo "  make test             Run tests"

install:
	poetry install

install-local:
	poetry install
	cd frontend && npm install

setup: install
	docker-compose up -d
	@echo "Waiting for services to start..."
	@sleep 10
	poetry run python scripts/init_db.py

setup-local: install-local check-local-services
	poetry run python scripts/init_db.py

dev-local: setup-local local

check-local-services:
	poetry run python scripts/check_local_services.py

local: check-local-services
	@echo "Starting API on http://localhost:8000"
	@echo "Starting frontend on http://localhost:5173"
	@trap 'kill $$api_pid $$frontend_pid 2>/dev/null || true' INT TERM EXIT; \
	poetry run uvicorn src.api.main:app --reload --port 8000 & \
	api_pid=$$!; \
	(cd frontend && npm run dev) & \
	frontend_pid=$$!; \
	wait -n $$api_pid $$frontend_pid

api:
	poetry run uvicorn src.api.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

start:
	docker-compose up -d

stop:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

init-db:
	poetry run python scripts/init_db.py

db-shell:
	docker exec -it postharvest-postgres psql -U scraper -d postharvest_scraper

dashboard:
	poetry run streamlit run dashboard/app.py

crawl-naro:
	poetry run python -c "from src.flows.discovery import discover_content; discover_content('naro')"

crawl-all:
	poetry run python -c "from src.flows.discovery import discover_all_sites; discover_all_sites()"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache
	rm -rf logs/*.log

test:
	poetry run pytest tests/ -v --tb=short

test-fast:
	poetry run pytest tests/ -q
