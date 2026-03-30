FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml .

# Install dependencies
RUN uv pip install --system -e .

# Copy application
COPY . .

# Expose port (Render uses $PORT env var)
EXPOSE $PORT

# Run application - use PORT env var from Render
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
