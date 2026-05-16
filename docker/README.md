# Docker

Local development and deployment layout for aicentral.

## Prerequisites

- Docker
- Docker Compose v2

## Setup

1. Copy environment file:

   ```bash
   cp docker/.env.example docker/.env
   ```

2. Edit `docker/.env` — set `LITELLM_MASTER_KEY` and provider API keys.

## Profiles

| Profile | Services | Command |
|---------|----------|---------|
| (default) | `db` only | `docker compose -f docker/docker-compose.yml up -d` |
| `litellm` | `db` + LiteLLM proxy | `docker compose -f docker/docker-compose.yml --profile litellm up -d` |
| `app` | `db` + aicentral app image | `docker compose -f docker/docker-compose.yml --profile app up -d --build` |

Run from the **repository root** or pass `-f docker/docker-compose.yml` from inside `docker/`.

## Verify

```bash
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f db
```

LiteLLM (when started): http://localhost:4000

## Stop

```bash
docker compose -f docker/docker-compose.yml down
```
