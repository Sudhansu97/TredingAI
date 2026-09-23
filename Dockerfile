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

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy dependency definitions and README required by hatchling
COPY pyproject.toml uv.lock README.md* ./

# If README.md doesn't exist locally, create a blank one so hatchling doesn't fail
RUN touch README.md
RUN uv sync --frozen --no-dev

# Copy project source code
COPY . .

# Default command to launch the live trading app
CMD ["uv", "run", "python", "scripts/telegram_bot.py"]