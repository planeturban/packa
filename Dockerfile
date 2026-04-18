FROM linuxserver/ffmpeg:latest

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY master/       master/
COPY slave/        slave/
COPY web/          web/
COPY shared/       shared/
COPY entrypoint.sh entrypoint.sh
RUN chmod +x entrypoint.sh

VOLUME ["/data"]

ENV PACKA_CONFIG=/data/packa.toml
ENV PACKA_ROLE=master

EXPOSE 9000 8000 8080

ENTRYPOINT ["/app/entrypoint.sh"]
