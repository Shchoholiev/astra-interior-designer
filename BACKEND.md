# Astra Interior Designer API

Python 3.12+ and FastAPI, using the reference folder layout with the package
named `astra_interior_designer` for this project.

## Run locally

From the repository root, with [uv](https://docs.astral.sh/uv/) installed:

```sh
uv sync
uv run fastapi dev
```

- Health: <http://127.0.0.1:8000/health>
- Swagger docs: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

`GET /health` returns `{"status":"ok"}`. The development server reloads when
Python files change.

For optional configuration, copy `.env.example` to `.env` and edit the values.
Settings use the `ASTRA_` prefix; environment variables override `.env` values.
Restart the server after changing settings. Defaults work without a `.env` file.

To run without development reload:

```sh
uv run uvicorn astra_interior_designer.main:app --host 0.0.0.0 --port 8000
```

## Structure

```text
src/astra_interior_designer/
├── api/
│   ├── __init__.py
│   ├── auth.py
│   ├── health.py
│   └── sessions.py
├── services/
│   └── __init__.py
├── __init__.py
├── app.py
├── config.py
├── dependencies.py
├── errors.py
├── main.py
└── supabase_persistence.py
```

`app.py` creates the application and registers routers; `main.py` exports the
ASGI application. `config.py` defines settings, and `dependencies.py` provides
cached settings for the application and future route dependencies.

Only health is implemented. The auth and sessions routers are registered and
ready for endpoints. `services/`, `errors.py`, and `supabase_persistence.py` are
placeholders for future business logic, error handling, and database access.
No authentication or database credentials are required to start this scaffold.

## Code checks

```sh
uv run ruff check src
uv run ruff format --check src
```

The router and settings setup follows the official FastAPI guides for
[multiple files](https://fastapi.tiangolo.com/tutorial/bigger-applications/) and
[environment settings](https://fastapi.tiangolo.com/advanced/settings/).
