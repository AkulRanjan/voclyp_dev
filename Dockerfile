# VoClyp — single artifact that runs the same way everywhere
# (your cloud, a partner's private cloud, or on-prem).
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY voclyp ./voclyp
COPY configs ./configs
COPY contracts ./contracts
COPY evals ./evals

# -e keeps the package at /app so configs/ resolve relative to the repo root
RUN pip install --no-cache-dir -e .[gateway,security]

RUN useradd --create-home --shell /usr/sbin/nologin voclyp \
    && mkdir -p /data && chown voclyp:voclyp /data
USER voclyp

ENV VOCLYP_DATA_DIR=/data
EXPOSE 8000

# Gateway by default; the worker runs the same image with a different command
# (see docker-compose.yml).
CMD ["uvicorn", "voclyp.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
