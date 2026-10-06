.PHONY: db api web test

db:
	docker compose up -d --wait

api:
	uv run --package northstar-api uvicorn northstar_api.main:app --app-dir apps/api --host 127.0.0.1 --port 8000

web:
	npm --prefix apps/web run dev

test:
	uv run pytest
