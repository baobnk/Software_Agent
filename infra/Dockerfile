FROM python:3.11-slim

WORKDIR /app

# System deps for pypdf, python-docx, openpyxl
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy wbs_agent_kit package (renderer + Pydantic types)
COPY packages/ packages/
RUN pip install --no-cache-dir packages/wbs_agent_kit/ 2>/dev/null || true

# Copy application code
COPY agents/ agents/
COPY tools/ tools/
COPY api/ api/
COPY config/ config/
COPY skills/ skills/
COPY memory/ memory/
COPY orchestrator.py .
COPY main.py .

# Create data directories (overridden by volume mounts)
RUN mkdir -p /data/attachments /data/outputs /data/workspace

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
