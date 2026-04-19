FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY alembic.ini ./
COPY alembic ./alembic

CMD ["python", "-m", "financial_assistant.main"]
