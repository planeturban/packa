FROM jellyfin/jellyfin-ffmpeg:latest AS jf-ffmpeg

FROM python:3.12-slim

# Copy Jellyfin ffmpeg (binary, ffprobe, and bundled shared libs).
# Only needed on slave nodes; master/web containers carry it too but
# don't invoke it — keeping a single image avoids separate builds.
COPY --from=jf-ffmpeg /usr/lib/jellyfin-ffmpeg /usr/lib/jellyfin-ffmpeg
RUN ln -s /usr/lib/jellyfin-ffmpeg/ffmpeg  /usr/local/bin/ffmpeg && \
    ln -s /usr/lib/jellyfin-ffmpeg/ffprobe /usr/local/bin/ffprobe

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY master/        master/
COPY slave/         slave/
COPY web/           web/
COPY shared/        shared/
COPY entrypoint.sh  entrypoint.sh
RUN chmod +x entrypoint.sh

# Data directory for SQLite databases and output files.
# Mount a volume here to persist data across container restarts.
VOLUME ["/data"]

# Default config path — override with -e PACKA_CONFIG=/path/to/packa.toml
# or by bind-mounting your config file to /data/packa.toml.
ENV PACKA_CONFIG=/data/packa.toml

# Which service to run: master (default), slave, or web.
# Override with -e PACKA_ROLE=slave or as the first argument.
ENV PACKA_ROLE=master

# Ports — match the defaults in packa.example.toml.
EXPOSE 9000 8000 8080

ENTRYPOINT ["/app/entrypoint.sh"]
