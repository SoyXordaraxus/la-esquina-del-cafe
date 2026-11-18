#!/usr/bin/env bash
# Arranca backend (8000) y frontend (5500) de La Esquina del Café con SQLite.
# Uso:
#   ./iniciar.sh         arranca usando la base existente (la crea si no existe)
#   ./iniciar.sh reset   borra backend/esquina.db, la vuelve a poblar y arranca
# Ctrl+C apaga los dos servidores.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$RAIZ/backend"
PUERTO="${PUERTO:-8000}"
PUERTO_WEB="${PUERTO_WEB:-5500}"
FRONTEND="$RAIZ/frontend"
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

# ---------- Frontend (servidor estático en segundo plano) ----------
if "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',$PUERTO_WEB))==0 else 1)"; then
    echo ">> El puerto $PUERTO_WEB ya está en uso: se asume que el frontend ya está encendido."
    PID_WEB=""
else
    "$PY" -m http.server "$PUERTO_WEB" --directory "$FRONTEND" >/dev/null 2>&1 &
    PID_WEB=$!
fi

# Al salir (Ctrl+C o error) se apaga también el frontend
apagar() {
    if [ -n "${PID_WEB:-}" ]; then kill "$PID_WEB" 2>/dev/null || true; fi
}
trap apagar EXIT INT TERM

# ---------- Codespaces: puerto 8000 público y direcciones listas ----------
if [ -n "${CODESPACE_NAME:-}" ]; then
    DOMINIO="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
    URL_WEB="https://$CODESPACE_NAME-$PUERTO_WEB.$DOMINIO"
    URL_API="https://$CODESPACE_NAME-$PUERTO.$DOMINIO"
    # Se intenta en segundo plano porque el puerto debe estar abierto primero
    ( sleep 4; gh codespace ports visibility "$PUERTO:public" -c "$CODESPACE_NAME" >/dev/null 2>&1 \
        || echo ">> No se pudo poner el puerto $PUERTO en Public: hazlo a mano en la pestaña Puertos." ) &
else
    URL_WEB="http://localhost:$PUERTO_WEB"
    URL_API="http://localhost:$PUERTO"
fi

echo ""
echo "=============================================================="
echo "  Caja:    $URL_WEB/caja.html"
echo "  Ventas:  $URL_WEB/ventas.html"
echo "  API:     $URL_API/docs"
echo "  Ctrl+C para apagar todo"
echo "=============================================================="
echo ""

# ---------- Backend (primer plano) ----------
"$PY" -m uvicorn main:app --host 0.0.0.0 --port "$PUERTO" --reload