#!/bin/sh
# Aplica las migraciones pendientes y arranca la API.
set -e
alembic upgrade head
# --proxy-headers: la auditoría registra la IP real del usuario y no la de nginx
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"