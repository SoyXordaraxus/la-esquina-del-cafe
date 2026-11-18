#!/usr/bin/env bash
# Arranca el backend de La Esquina del Café con SQLite.
# Uso:
#   ./iniciar.sh         arranca usando la base existente (la crea si no existe)
#   ./iniciar.sh reset   borra backend/esquina.db, la vuelve a poblar y arranca
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$RAIZ/backend"
PUERTO="${PUERTO:-8000}"
DB_FILE="$BACKEND/esquina.db"

case "${1:-}" in
    "") ;;
    reset)
        if [ -f "$DB_FILE" ]; then
            echo ">> reset: borrando backend/esquina.db"
            rm -f "$DB_FILE"
        else
            echo ">> reset: backend/esquina.db no existía"
        fi
        ;;
    *)
        echo "Uso: $0 [reset]" >&2
        exit 1
        ;;
esac

# Los imports del backend son relativos a backend/ (from database import ...),
# y la ruta ./esquina.db también, así que todo se ejecuta desde ahí.
cd "$BACKEND"

export DATABASE_URL="${DATABASE_URL:-sqlite:///./esquina.db}"

# Python: usa el venv si existe, si no python3 del sistema
if [ -x "$RAIZ/venv/bin/python" ]; then
    PY="$RAIZ/venv/bin/python"
else
    PY="python3"
fi

# Verificar dependencias mínimas
if ! "$PY" -c "import fastapi, uvicorn, sqlalchemy" 2>/dev/null; then
    echo ">> Faltan dependencias. Instala con:"
    echo "   $PY -m pip install -r \"$RAIZ/requirements.txt\""
    exit 1
fi

# Crear y poblar la base solo si no existe
if [ ! -f "$DB_FILE" ]; then
    echo ">> esquina.db no existe: creando tablas y datos iniciales (seed.py)..."
    "$PY" seed.py
else
    echo ">> Usando base existente: backend/esquina.db"
fi

echo ">> API en http://localhost:$PUERTO  (docs: http://localhost:$PUERTO/docs)"
exec "$PY" -m uvicorn main:app --host 0.0.0.0 --port "$PUERTO" --reload
