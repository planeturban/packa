FROM python:3.12-slim

# ffmpeg is only needed on slave nodes; installing it in the base image
# keeps things simple — master/web containers pay ~80 MB extra but avoid
# a separate image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY master/   master/
COPY slave/    slave/
COPY web/      web/
COPY shared/   shared/

# Data directory for SQLite databases and output files.
# Mount a volume here to persist data across container restarts.
VOLUME ["/data"]

# Default config path — override with -e PACKA_CONFIG=/path/to/packa.toml
# or by bind-mounting your config file to /data/packa.toml.
ENV PACKA_CONFIG=/data/packa.toml

# Ports — match the defaults in packa.example.toml.
# Override via config or environment variables.
EXPOSE 9000 8000 8080

CMD ["python", "-m", "master.master", "--config", "/data/packa.toml", "--bind", "any"]

# Override for other services:
#   docker run packa python -m slave.main --config /data/packa.toml --bind any
#   docker run packa python -m web.main   --config /data/packa.toml --bind any
