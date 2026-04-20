FROM linuxserver/ffmpeg:latest

ARG PACKA_VERSION=dev
ARG PACKA_COMMIT=local
ENV PACKA_VERSION=$PACKA_VERSION
ENV PACKA_COMMIT=$PACKA_COMMIT

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY master/       master/
COPY worker/        worker/
COPY web/          web/
COPY shared/       shared/
COPY entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh

VOLUME ["/data"]

ENV PACKA_CONFIG=/data/packa.toml
ENV PACKA_ROLE=master

EXPOSE 9000 8000 8080

ENTRYPOINT ["/app/entrypoint.sh"]
