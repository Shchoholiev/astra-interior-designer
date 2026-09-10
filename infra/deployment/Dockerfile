# Build only the context printed by prepare_backend_build.py --dockerfile.
FROM python:3.14-slim

WORKDIR /opt/astra

COPY pyproject.toml uv.lock requirements.txt BACKEND.md ./
COPY src/ ./src/

RUN python -m venv /opt/astra/.venv \
    && /opt/astra/.venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /opt/astra/.venv/bin/pip install --no-cache-dir --no-deps .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["/opt/astra/.venv/bin/python", "-m", "uvicorn", "astra_interior_designer.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "25"]
