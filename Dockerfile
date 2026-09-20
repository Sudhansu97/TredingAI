FROM python:3.11-slim

# Prevent Python from writing bytecode and enable unbuffered logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off

# Install system dependencies and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git build-essential \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && rm -rf /var/lib/apt/get/lists/*

ENV PATH="/root/.cargo/bin:$PATH"

WORKDIR /app

# Copy dependency definitions first for Docker layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy project source code
COPY . .

# Default command to launch the live trading app
CMD ["uv", "run", "python", "scripts/run_live_trading.py"]