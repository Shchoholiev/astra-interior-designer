# Astra Interior Designer API

Python 3.12+. Run from the repository root:

```sh
uv sync
uv run fastapi dev
```

API docs: <http://127.0.0.1:8000/docs>. No endpoints are implemented yet.

```text
src/astra_interior_designer/
├── api/
│   └── __init__.py
├── services/
│   └── __init__.py
├── __init__.py
└── main.py
```

```sh
uv run ruff check src
uv run ruff format --check src
```
