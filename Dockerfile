FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /bin/uv

# Carlito is metric-compatible with Calibri, the AA house font, for screener charts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-crosextra-carlito \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install exactly the versions in uv.lock so a new upstream release
# (e.g. mcp 2.x) can't break a deploy.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"
# Build matplotlib's font cache now rather than on the first screener request.
RUN python -c "import matplotlib.font_manager"

COPY main.py .
COPY app/ app/

CMD ["python", "main.py"]
