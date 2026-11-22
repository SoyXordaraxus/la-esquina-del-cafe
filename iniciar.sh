#!/usr/bin/env bash
# Arranca La Esquina del Café: FastAPI (8000) sirve el API y también el frontend.
# Uso:
#   ./iniciar.sh               SQLite (backend/esquina.db); la crea si no existe
#   ./iniciar.sh reset         SQLite: borra la base, la vuelve a poblar y arranca
#   ./iniciar.sh mysql         MySQL 8 en Docker (contenedor mysql-cafe); lo crea/enciende si hace falta
#   ./iniciar.sh mysql reset   MySQL: borra la base, la vuelve a poblar y arranca
# Ctrl+C apaga el servidor (MySQL se queda encendido).
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$RAIZ/backend"
PUERTO="${PUERTO:-8000}"
DB_FILE="$BACKEND/esquina.db"

# Datos del contenedor MySQL
MYSQL_CONTENEDOR="mysql-cafe"
MYSQL_BD="la_esquina_del_cafe"
MYSQL_USUARIO="cafe"
MYSQL_CLAVE="cafe1234"
MYSQL_ROOT_CLAVE="cafe1234"
URL_MYSQL="mysql+pymysql://$MYSQL_USUARIO:$MYSQL_CLAVE@127.0.0.1:3306/$MYSQL_BD"

# ---------- Argumentos ----------
MOTOR="sqlite"
RESET="no"
for arg in "$@"; do
    case "$arg" in
        mysql) MOTOR="mysql" ;;
        reset) RESET="si" ;;
        *) echo "Uso: $0 [mysql] [reset]" >&2; exit 1 ;;
    esac
done

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

# Los imports del backend son relativos a backend/ (from database import ...)
cd "$BACKEND"

# ---------- Preparar la base de datos ----------
if [ "$MOTOR" = "mysql" ]; then
    export DATABASE_URL="$URL_MYSQL"

    if ! "$PY" -c "import pymysql" 2>/dev/null; then
        echo ">> Falta pymysql. Instala con: $PY -m pip install -r \"$RAIZ/requirements.txt\""
        exit 1
    fi
    if ! command -v docker >/dev/null 2>&1; then
        echo ">> Docker no está disponible en este equipo."
        exit 1
    fi

    # Crear o encender el contenedor
    if ! docker ps -a --format '{{.Names}}' | grep -qx "$MYSQL_CONTENEDOR"; then
        echo ">> Creando contenedor MySQL 8 ($MYSQL_CONTENEDOR)..."
        docker run -d --name "$MYSQL_CONTENEDOR" -p 3306:3306 --restart unless-stopped \
            -e MYSQL_ROOT_PASSWORD="$MYSQL_ROOT_CLAVE" -e MYSQL_DATABASE="$MYSQL_BD" \
            -e MYSQL_USER="$MYSQL_USUARIO" -e MYSQL_PASSWORD="$MYSQL_CLAVE" mysql:8.0 >/dev/null
    elif ! docker ps --format '{{.Names}}' | grep -qx "$MYSQL_CONTENEDOR"; then
        echo ">> Encendiendo contenedor $MYSQL_CONTENEDOR..."
        docker start "$MYSQL_CONTENEDOR" >/dev/null
    fi

    # Esperar a que MySQL acepte conexiones desde Python (máx. ~2 min)
    echo -n ">> Esperando a MySQL"
    LISTO="no"
    for _ in $(seq 1 60); do
        if "$PY" -c "import pymysql; pymysql.connect(host='127.0.0.1', port=3306, user='$MYSQL_USUARIO', password='$MYSQL_CLAVE', database='$MYSQL_BD').close()" 2>/dev/null; then
            LISTO="si"; break
        fi
        echo -n "."; sleep 2
    done
    echo ""
    if [ "$LISTO" != "si" ]; then
        echo ">> MySQL no respondió. Revisa: docker logs $MYSQL_CONTENEDOR"
        exit 1
    fi

    if [ "$RESET" = "si" ]; then
        echo ">> reset: borrando y creando de nuevo la base $MYSQL_BD en MySQL"
        docker exec "$MYSQL_CONTENEDOR" mysql -uroot -p"$MYSQL_ROOT_CLAVE" -e \
            "DROP DATABASE IF EXISTS $MYSQL_BD; CREATE DATABASE $MYSQL_BD CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; GRANT ALL ON $MYSQL_BD.* TO '$MYSQL_USUARIO'@'%';" 2>/dev/null
    fi

    # Poblar solo si la base está vacía (no existe la tabla usuario)
    if "$PY" -c "
import sys
from sqlalchemy import create_engine, inspect
sys.exit(0 if inspect(create_engine('$URL_MYSQL')).has_table('usuario') else 1)"; then
        echo ">> Usando base MySQL existente: $MYSQL_BD"
    else
        echo ">> Base MySQL vacía: creando tablas y datos iniciales (seed.py)..."
        "$PY" seed.py
    fi
    DESCRIPCION_BD="MySQL 8 ($MYSQL_CONTENEDOR / $MYSQL_BD)"
else
    export DATABASE_URL="sqlite:///./esquina.db"

    if [ "$RESET" = "si" ]; then
        echo ">> reset: borrando backend/esquina.db"
        rm -f "$DB_FILE"
    fi
    if [ ! -f "$DB_FILE" ]; then
        echo ">> esquina.db no existe: creando tablas y datos iniciales (seed.py)..."
        "$PY" seed.py
    else
        echo ">> Usando base SQLite existente: backend/esquina.db"
    fi
    DESCRIPCION_BD="SQLite (backend/esquina.db)"
fi

# ---------- Direcciones ----------
URL_BASE="http://127.0.0.1:$PUERTO"

echo ""
echo "=============================================================="
echo "  Base de datos: $DESCRIPCION_BD"
echo "  Abrir:   $URL_BASE/login.html"
echo "  API:     $URL_BASE/docs"
if [ -n "${CODESPACE_NAME:-}" ]; then
    # En Codespaces el navegador entra por el puerto reenviado
    DOMINIO="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
    echo "  Codespaces: https://$CODESPACE_NAME-$PUERTO.$DOMINIO/login.html"
fi
echo "  Ctrl+C para apagar"
echo "=============================================================="
echo ""

# ---------- Backend (primer plano) ----------
exec "$PY" -m uvicorn main:app --host 0.0.0.0 --port "$PUERTO" --reload