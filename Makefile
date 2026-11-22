.PHONY: install dev backend frontend build test lint run docker

install:            ## instala dependências (backend + frontend)
	pip install -r backend/requirements-dev.txt
	cd frontend && npm ci

backend:            ## API em modo desenvolvimento (http://localhost:8000)
	cd backend && uvicorn mlstudio.api.main:app --reload --port 8000

frontend:           ## UI em modo desenvolvimento (http://localhost:5173, proxy para a API)
	cd frontend && npm run dev

build:              ## compila o frontend (servido pela API em /)
	cd frontend && npm run build

run: build          ## aplicação completa em http://localhost:8000
	cd backend && uvicorn mlstudio.api.main:app --host 0.0.0.0 --port 8000

test:               ## testes do backend + verificação de tipos do frontend
	cd backend && python -m pytest -q
	cd frontend && npx tsc --noEmit -p tsconfig.json

lint:
	cd backend && ruff check mlstudio tests

docker:             ## imagem Docker com tudo incluído
	docker compose up --build
