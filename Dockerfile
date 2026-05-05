FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[postgres]"

# Copy application
COPY . .

# Run migrations and start server
CMD ["sh", "-c", "alembic upgrade head && fastapi run app/main.py --host 0.0.0.0 --port 8000"]
