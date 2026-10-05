FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service
COPY pyproject.toml README.md ./
COPY app ./app
COPY tests ./tests
COPY contracts ./contracts
COPY docs ./docs
COPY frontend/src ./frontend/src
COPY ARCHITECTURE.md Dockerfile docker-compose.yml ./
RUN pip install --no-cache-dir '.[dev]'

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

