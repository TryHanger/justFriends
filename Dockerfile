FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /service
COPY pyproject.toml README.md ./
COPY app ./app
COPY tests ./tests
COPY contracts ./contracts
# Lexicons, RAG knowledge base, few-shot examples and normalization tables are runtime data.
COPY data ./data
COPY experiments ./experiments
COPY annotation ./annotation
COPY docs ./docs
COPY frontend/src ./frontend/src
COPY ARCHITECTURE.md Dockerfile docker-compose.yml ./
COPY .github ./.github
RUN pip install --no-cache-dir '.[dev]'
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

