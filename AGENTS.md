# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Python knowledge pipeline and API under `src/`, a React/Vite chat and admin frontend under `frontend/`, and supporting operational files in `docker/`, `scripts/`, and `docs/`. Backend routes live in `src/api/routes/`, service logic in `src/api/services/`, extraction code in `src/extractors/`, scraping and ingestion flows in `src/flows/`, and persistence integrations in `src/storage/`. Tests are in `tests/` and generally mirror backend modules. Source PDFs and reference literature are stored in `literature/`.

## Build, Test, and Development Commands

- `poetry install`: install Python backend dependencies.
- `make install-local`: install app dependencies.
- `make setup-local`: check local PostgreSQL, Qdrant, and MinIO, then initialize the DB.
- `make dev-local`: run non-Docker setup, then start API and frontend.
- `make local`: run the API and Vite frontend together outside Docker.
- `make start` / `make stop`: start or stop Docker Compose services.
- `make init-db`: initialize PostgreSQL schema.
- `make test` or `poetry run pytest tests/ -v --tb=short`: run the backend test suite.
- `cd frontend && npm run build`: create a production frontend build.

## Coding Style & Naming Conventions

Python targets 3.11 with 100-character lines. Use Black and Ruff settings from `pyproject.toml`; run `poetry run black src tests scripts` and `poetry run ruff check src tests scripts` before larger changes. Prefer snake_case for Python modules, functions, and test names. React components use PascalCase filenames such as `ChatWindow.jsx`; hooks use `useSomething.js`; shared UI primitives live in `frontend/src/components/ui/`.

## Testing Guidelines

Use pytest for backend tests. Name test files `test_*.py` and place shared fixtures in `tests/conftest.py`. Add focused tests for API services, storage integrations, extraction logic, translation behavior, and webhook handling when modifying those areas. For frontend changes, run `npm run build`; add manual browser checks for chat, admin, and responsive layout changes.

## Commit & Pull Request Guidelines

Recent history uses short imperative subjects, often Conventional Commit prefixes such as `feat:` and `fix:`. Keep commits scoped, for example `fix: handle empty search results` or `feat: add manual ingestion status`. Pull requests should include a brief summary, test commands run, linked issue or context, and screenshots or screen recordings for frontend/admin UI changes.

## Security & Configuration Tips

Keep secrets out of git. Configure API keys, model provider settings, database URLs, WhatsApp credentials, and admin credentials through local environment files or deployment configuration. Avoid committing generated logs, local caches, or downloaded credentials.
