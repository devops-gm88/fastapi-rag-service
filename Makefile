PY      ?= .venv/bin/python
PIP     ?= .venv/bin/pip
UVICORN ?= .venv/bin/uvicorn
PYTEST  ?= .venv/bin/pytest
PG_BIN  ?=
BASE    ?= http://127.0.0.1:8000

.DEFAULT_GOAL := help

help:
	@echo "make install  create .venv and install dependencies"
	@echo "make db       create the local database and the vector extension"
	@echo "make run      run the service with uvicorn --reload"
	@echo "make test     run the pytest suite"
	@echo "make up       docker compose up --build -d   (needs Docker)"
	@echo "make down     docker compose down -v"
	@echo "make health   curl GET /health"
	@echo "make query    curl POST /query"
	@echo "make ingest   curl POST /ingest"

install:
	python3 -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -r requirements-dev.txt

db:
	PG_BIN="$(PG_BIN)" bash scripts/local_db.sh

run:
	$(UVICORN) app.main:app --reload --host 127.0.0.1 --port 8000

test:
	$(PYTEST)

up:
	docker compose up --build -d

down:
	docker compose down -v

health:
	@curl -sS $(BASE)/health | $(PY) -m json.tool

query:
	@curl -sS -X POST $(BASE)/query -H 'content-type: application/json' \
	  -d '{"question":"How many vehicles are in the Acme Fleet pilot?","k":3}' | $(PY) -m json.tool

ingest:
	@curl -sS -X POST $(BASE)/ingest -H 'content-type: application/json' \
	  -d '{"source_path":"fleet_overview.md"}' | $(PY) -m json.tool

openapi:
	@curl -sS $(BASE)/openapi.json | $(PY) -c 'import json,sys; print("\n".join(sorted(json.load(sys.stdin)["paths"])))'

.PHONY: help install db run test up down health query ingest openapi
