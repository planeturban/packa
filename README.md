# Packa

> **Note:** This project is 100% AI-generated using [Claude](https://claude.ai) by Anthropic. Do with this information as you wish.

Packa is a distributed video conversion system. A **master** node manages a queue of files and distributes work to one or more **slave** nodes. Slaves pull jobs, run ffmpeg to convert to HEVC, and report results back. A **web** frontend provides a browser dashboard for monitoring and control.

Files are never transferred over the network — slaves access them directly via the filesystem.

Encoder support is fully config-driven — each encoder is defined as a set of ffmpeg arguments in `packa.toml`. Any encoder supported by the ffmpeg build in use will work. The Docker image is based on [`linuxserver/ffmpeg`](https://github.com/linuxserver/docker-ffmpeg), so any hardware encoder supported by that image works out of the box.

---

## Quick start

```bash
cp packa.example.toml packa.toml
# edit packa.toml to match your setup
docker compose up
```

The compose file expects `packa.toml` in the current directory. A single image covers all three roles, selected via the `PACKA_ROLE` environment variable (`master`, `slave`, or `web`).

---

## Security

Packa has no authentication between nodes and is intended for use on trusted networks only. See [Architecture — Security](docs/architecture.md#security) for details.

---

## Documentation

- [Configuration](docs/configuration.md) — config file reference, environment variables, encoder presets
- [Architecture](docs/architecture.md) — pull model, path prefix translation, databases, file status lifecycle
- [API reference](docs/api.md) — master and slave HTTP endpoints
