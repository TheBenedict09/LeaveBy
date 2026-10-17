.PHONY: dev test lint fmt openapi web rail-data
dev:
	cd backend && uvicorn app.main:app --reload --port 8000

test:
	cd backend && python -m pytest -q

lint:
	cd backend && ruff check . && ruff format --check .

fmt:
	cd backend && ruff check --fix . && ruff format .

openapi:
	python scripts/export_openapi.py

rail-data:
	python scripts/build_rail_timetable.py
