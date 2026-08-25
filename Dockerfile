FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

COPY evidence_agent ./evidence_agent
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

CMD exec uvicorn evidence_agent.main:app --host 0.0.0.0 --port "$PORT"
