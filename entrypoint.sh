#!/bin/bash

set -e

echo "Rodando migrações do banco de dados..."
alembic upgrade head

echo "Efetuando seed do banco de dados..."
python -m app.infra.db.seed

echo "Iniciando o servidor FastAPI..."
exec fastapi run --port 8000 --host 0.0.0.0
