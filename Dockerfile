FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal; wheels cover the rest.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY aiapiradar ./aiapiradar

# Non-root + writable data dir for the SQLite file.
RUN useradd --create-home --uid 1000 radar \
    && mkdir -p /data && chown -R radar:radar /data /app
USER radar

ENV AIRADAR_DB_URL=sqlite:////data/aiapiradar.db

# Default: run the collector scheduler. compose overrides for the web service.
ENTRYPOINT ["python", "-m", "aiapiradar.cli"]
CMD ["run"]
