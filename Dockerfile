FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 TZ=UTC DATA_PROVIDER=twelvedata
WORKDIR /app

COPY requirements-worker.txt ./
RUN python -m pip install --no-cache-dir -r requirements-worker.txt

RUN useradd --create-home --uid 10001 trader
COPY --chown=trader:trader *.py ./
USER trader

# No HTTP port: this container runs the background monitor only.
CMD ["python", "worker.py"]
