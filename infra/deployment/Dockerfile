# Build only the context printed by prepare_backend_build.py --dockerfile.
FROM python:3.14-slim

WORKDIR /opt/astra

COPY pyproject.toml uv.lock requirements.txt BACKEND.md ./
COPY src/ ./src/
COPY wheels/agent_api_sdk-*-py3-none-any.whl /tmp/astra-sdk/

# The private SDK wheel is built locally from the commit in the unchanged lock.
# No GitHub access or runtime credentials are needed during the image build.
RUN python -m venv /opt/astra/.venv \
    && /opt/astra/.venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /opt/astra/.venv/bin/pip install --no-cache-dir --no-deps /tmp/astra-sdk/*.whl . \
    && rm -rf /tmp/astra-sdk

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["/opt/astra/.venv/bin/python", "-m", "uvicorn", "astra_interior_designer.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "25"]
