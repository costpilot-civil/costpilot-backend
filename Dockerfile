
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/costpilot-backend/.venv/bin:$PATH"

WORKDIR /app/costpilot-backend

# Copy Backend and its local Core dependency
COPY costpilot-core/ /app/costpilot-core/
COPY costpilot-backend/ /app/costpilot-backend/

# Install production dependencies
RUN uv sync --locked --no-dev

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
