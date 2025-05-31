FROM python:3.13

WORKDIR /app

# Настройка uv
RUN apt-get update && apt-get install -y curl wget

ADD https://astral.sh/uv/install.sh /uv-installer.sh

RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

COPY pyproject.toml .
COPY uv.lock .

RUN uv sync --no-install-project

ENV PATH="/app/.venv/bin/:$PATH"

COPY . .

ENV PYTHONPATH=/app

CMD ["uv", "run", "main.py"]
