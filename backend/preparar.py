"""
Ayudante de arranque para iniciar.bat (Windows). También funciona en Linux/macOS.

Uso (desde backend/, con DATABASE_URL ya definida):
    python preparar.py deps [mysql]   Revisa que las dependencias estén instaladas.
    python preparar.py bd [reset]     Revisa la conexión, crea la base si no existe
                                      y la puebla con seed.py si está vacía.
                                      Con "reset" la borra y la vuelve a poblar.
    python preparar.py puerto 8000 [host]  Revisa que el puerto esté libre.
    python preparar.py navegador URL  Espera a que el servidor responda y abre el navegador.

Termina con código 0 si todo salió bien y 1 si hubo un problema (con el mensaje en español).
"""
import importlib
import os
import socket
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

CARPETA_BACKEND = Path(__file__).resolve().parent

# módulo que se importa -> paquete que se instala con pip
DEPENDENCIAS = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "jose": "python-jose[cryptography]",
    "tzdata": "tzdata",
    "fpdf": "fpdf2",
}
DEPENDENCIAS_MYSQL = {"pymysql": "pymysql", "cryptography": "cryptography"}


def error(mensaje: str) -> int:
    print(f"\n[ERROR] {mensaje}\n", file=sys.stderr)
    return 1


# ---------------------------------------------------------
def revisar_dependencias(con_mysql: bool) -> int:
    requeridas = dict(DEPENDENCIAS, **(DEPENDENCIAS_MYSQL if con_mysql else {}))
    faltan = []
    for modulo, paquete in requeridas.items():
        try:
            importlib.import_module(modulo)
        except ImportError:
            faltan.append(paquete)
    if sys.version_info < (3, 12):
        print(f"[AVISO] Estás usando Python {sys.version.split()[0]}; el proyecto requiere Python 3.12 o superior.")
    if faltan:
        return error(
            "Faltan dependencias de Python: " + ", ".join(faltan) + "\n"
            "        Instálalas desde la carpeta del proyecto con:\n"
            f"          \"{sys.executable}\" -m pip install -r requirements.txt"
        )
    print(">> Dependencias de Python: OK")
    return 0


# ---------------------------------------------------------
def _url_bd():
    from sqlalchemy.engine import make_url

    valor = os.getenv("DATABASE_URL", "").strip()
    if not valor:
        return None, error(
            "No está definida DATABASE_URL.\n"
            "        Copia .env.ejemplo como .env (en la carpeta del proyecto) y ajusta la conexión a MySQL,\n"
            "        o usa el modo SQLite:  iniciar.bat sqlite"
        )
    try:
        return make_url(valor), 0
    except Exception:
        return None, error(f"DATABASE_URL no tiene un formato válido: {valor}")


def _base_poblada() -> bool:
    from sqlalchemy import create_engine, inspect

    motor = create_engine(os.environ["DATABASE_URL"])
    try:
        return inspect(motor).has_table("usuario")
    finally:
        motor.dispose()


def _poblar() -> None:
    sys.path.insert(0, str(CARPETA_BACKEND))
    import seed  # lee DATABASE_URL al importarse (database.py)

    seed.poblar_base()


def preparar_sqlite(url, reset: bool) -> int:
    ruta = Path(url.database or "")
    if not ruta.is_absolute():
        ruta = Path.cwd() / ruta
    if reset and ruta.exists():
        print(f">> reset: borrando {ruta}")
        ruta.unlink()
    if ruta.exists() and _base_poblada():
        print(f">> Usando base SQLite existente: {ruta}")
        return 0
    print(">> Base SQLite vacía: creando tablas y datos iniciales (seed.py)...")
    _poblar()
    return 0


def preparar_mysql(url, reset: bool) -> int:
    import pymysql

    nombre_bd = url.database
    if not nombre_bd:
        return error("DATABASE_URL no indica el nombre de la base (…:3306/la_esquina_del_cafe).")
    host, puerto = url.host or "127.0.0.1", url.port or 3306
    try:
        conexion = pymysql.connect(
            host=host, port=puerto, user=url.username or "root", password=url.password or "",
            connect_timeout=5, charset="utf8mb4",
        )
    except pymysql.err.OperationalError as e:
        codigo = e.args[0] if e.args else None
        if codigo == 1045:
            return error(
                f"MySQL rechazó el usuario '{url.username}' (usuario o contraseña incorrectos).\n"
                "        Revisa DATABASE_URL en el archivo .env."
            )
        return error(
            f"MySQL no responde en {host}:{puerto}.\n"
            "        - Verifica que MySQL 8 esté instalado y el servicio encendido\n"
            "          (Servicios de Windows > MySQL80 > Iniciar, o en una terminal de administrador: net start MySQL80).\n"
            "        - Revisa el host y el puerto de DATABASE_URL en el archivo .env.\n"
            "        - Si no tienes MySQL, puedes usar el plan B:  iniciar.bat sqlite\n"
            f"        Detalle: {e}"
        )
    try:
        with conexion.cursor() as cur:
            if reset:
                print(f">> reset: borrando la base {nombre_bd} en MySQL")
                cur.execute(f"DROP DATABASE IF EXISTS `{nombre_bd}`")
            cur.execute("SHOW DATABASES LIKE %s", (nombre_bd,))
            if cur.fetchone() is None:   # solo se pide permiso de crear si hace falta
                print(f">> Creando la base {nombre_bd} en MySQL")
                cur.execute(
                    f"CREATE DATABASE `{nombre_bd}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        conexion.commit()
    except pymysql.err.MySQLError as e:
        return error(
            f"No se pudo crear/borrar la base {nombre_bd}: {e}\n"
            f"        El usuario '{url.username}' necesita permiso para crear bases de datos,\n"
            "        o crea la base a mano en MySQL Workbench y vuelve a intentar."
        )
    finally:
        conexion.close()

    if _base_poblada():
        print(f">> Usando base MySQL existente: {nombre_bd}")
        return 0
    print(f">> Base MySQL vacía: creando tablas y datos iniciales en {nombre_bd} (seed.py)...")
    _poblar()
    return 0


def preparar_bd(reset: bool) -> int:
    url, codigo = _url_bd()
    if codigo:
        return codigo
    motor = url.get_backend_name()
    if motor == "sqlite":
        return preparar_sqlite(url, reset)
    if motor == "mysql":
        return preparar_mysql(url, reset)
    return error(f"Motor de base de datos no soportado: {motor} (usa mysql+pymysql o sqlite).")


# ---------------------------------------------------------
def _puerto_ocupado(puerto: int, host: str) -> bool:
    # 1) ¿alguien ya responde ahí?  2) ¿se puede abrir?  (en Windows hacen falta las dos)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        if s.connect_ex(("127.0.0.1", puerto)) == 0:
            return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, puerto))
        except OSError:
            return True
    return False


def revisar_puerto(puerto: int, host: str = "127.0.0.1") -> int:
    if _puerto_ocupado(puerto, host):
        return error(
            f"El puerto {puerto} ya está en uso (\"Address already in use\").\n"
            "        Probablemente el sistema ya está abierto en otra ventana: ciérrala con Ctrl+C,\n"
            f"        o usa otro puerto poniendo PUERTO=8001 en el archivo .env.\n"
            f"        Para ver qué programa lo usa:  netstat -ano | findstr :{puerto}"
        )
    return 0


def abrir_navegador(url: str, espera_max: float = 60) -> int:
    """Espera a que uvicorn responda y abre el navegador (se lanza en segundo plano)."""
    fin = time.time() + espera_max
    while time.time() < fin:
        try:
            urllib.request.urlopen(url, timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    webbrowser.open(url)
    return 0


# ---------------------------------------------------------
def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 1
    orden, resto = argv[0], argv[1:]
    try:
        if orden == "deps":
            return revisar_dependencias("mysql" in resto)
        if orden == "bd":
            return preparar_bd("reset" in resto)
        if orden == "puerto":
            return revisar_puerto(int(resto[0]) if resto else 8000, resto[1] if len(resto) > 1 else "127.0.0.1")
        if orden == "navegador":
            return abrir_navegador(resto[0] if resto else "http://127.0.0.1:8000/login.html")
    except Exception as e:  # cualquier otra falla: mensaje legible en vez de traza
        return error(f"{type(e).__name__}: {e}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
