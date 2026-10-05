FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /bin/uv

WORKDIR /app

# Install exactly the versions in uv.lock so a new upstream release
# (e.g. mcp 2.x) can't break a deploy.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY main.py .
COPY app/ app/

ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "main.py"]
