# Packa

Distributed system for transferring video files from a master to one or more slaves. The master receives file paths via API, collects metadata, and distributes files to registered slaves using round-robin.

## Architecture

```
master/          — receives file paths, collects metadata, distributes to slaves
slave/           — receives metadata and files, stores in database and on disk
shared/          — common models, schemas and CRUD (used by both)
```

### Ports

| Service              | Protocol | Default |
|----------------------|----------|---------|
| Master API           | HTTP     | 9000    |
| Slave metadata API   | HTTP     | 8000    |
| Slave file transfer  | TCP      | 8001    |

### Databases

Each node has its own SQLite database with an identical schema. The master assigns the ID — the slave stores the record under the same ID.

| Node   | File       |
|--------|------------|
| Master | master.db  |
| Slave  | slave.db   |

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Running

### Master

```bash
python -m master.master [--bind ADDRESS] [--api-port PORT]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--bind` | `0.0.0.0` | Address to bind the API server to |
| `--api-port` | `9000` | API port |

**Example:**
```bash
python -m master.master --bind 0.0.0.0 --api-port 9000
```

### Slave

```bash
python -m slave.main [--bind ADDRESS] [--api-port PORT] [--file-port PORT]
                     [--master-host HOST] [--master-port PORT]
                     [--advertise-host HOST]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--bind` | `0.0.0.0` | Address to bind both servers to |
| `--api-port` | `8000` | Metadata API port |
| `--file-port` | `8001` | File transfer TCP port |
| `--master-host` | — | Master hostname/IP to register with (omit to run standalone) |
| `--master-port` | `9000` | Master API port |
| `--advertise-host` | auto | Hostname/IP advertised to master. Auto-detected if omitted |

**Example:**
```bash
python -m slave.main --master-host 192.168.1.5 --advertise-host 192.168.1.10
```

---

## API

### Master API (port 9000)

#### Register a slave
```
POST /slaves
```
```json
{
  "host": "192.168.1.10",
  "api_port": 8000,
  "file_port": 8001
}
```

#### List slaves
```
GET /slaves
```

#### Deregister a slave
```
DELETE /slaves/{id}
```

#### Start a transfer
```
POST /transfer
```
```json
{
  "file_path": "/media/videos/film.mkv"
}
```

Response `202 Accepted`:
```json
{
  "record_id": 42,
  "slave_id": 1,
  "slave_host": "192.168.1.10",
  "file_name": "film.mkv",
  "checksum": "a3f9..."
}
```

Metadata is created synchronously. The file transfer runs in the background — poll status via `GET /files/{record_id}`.

#### Get records
```
GET /files
GET /files/{id}
```

---

### Slave API (port 8000)

#### Get records
```
GET /files
GET /files/{id}
```

Response:
```json
{
  "id": 42,
  "file_name": "film.mkv",
  "file_path": "/media/videos/film.mkv",
  "c_time": 1744123456.789,
  "m_time": 1744123456.789,
  "checksum": "a3f9...",
  "status": "complete",
  "created_at": "2026-04-14T19:00:00+00:00",
  "updated_at": "2026-04-14T19:00:45+00:00"
}
```

#### Update status manually
```
PATCH /files/{id}/status
```
```json
{ "status": "error" }
```

---

## Status values

| Status | Description |
|--------|-------------|
| `pending` | Record created, transfer not yet started |
| `transferring` | File is currently being transferred |
| `complete` | Transfer finished successfully |
| `error` | An error occurred during transfer |

---

## Checksum

SHA-256 of the concatenated metadata fields:

```
SHA-256("{file_name}{file_path}{c_time}{m_time}")
```

The ID is not included in the calculation.

---

## File transfer protocol (TCP)

Master and slave communicate on port 8001 using the following protocol:

```
[8 bytes]   uint64 big-endian — length of the JSON header
[N bytes]   JSON header: {"record_id": int, "file_name": str, "file_size": int}
[N bytes]   raw file bytes
[2-5 bytes] response from slave: "OK" or "ERROR"
```

Received files are stored in the `uploads/` directory on the slave, named `{record_id}_{file_name}`.

---

## Example — complete flow

```bash
# 1. Start master
python -m master.master

# 2. Start one or more slaves (each slave registers with master automatically)
python -m slave.main --master-host localhost --advertise-host 192.168.1.10
python -m slave.main --master-host localhost --advertise-host 192.168.1.11 \
                     --api-port 8100 --file-port 8101

# 3. Trigger a transfer
curl -X POST http://localhost:9000/transfer \
     -H "Content-Type: application/json" \
     -d '{"file_path": "/media/videos/film.mkv"}'

# 4. Poll status
curl http://localhost:9000/files/42
curl http://192.168.1.10:8000/files/42
```
