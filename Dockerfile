FROM python:3.12.4-slim-bookworm@sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv==0.9.3
WORKDIR /app
COPY . /app
RUN uv sync --locked --all-packages --no-dev && useradd --uid 10001 --create-home reputation && mkdir -p /app/artifacts/evidence /app/artifacts/fixtures && chown -R reputation:reputation /app
USER 10001:10001
ENV PATH="/app/.venv/bin:$PATH" REPUTATION_ROOT=/app
CMD ["uvicorn", "reputation_platform.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
