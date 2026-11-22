
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Obtener la dirección de conexión desde una variable de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "No se ha configurado la variable de entorno DATABASE_URL"
    )

# Crear la conexión con MySQL
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

# Las fechas-hora se guardan en UTC (ver services/tiempo.py). En MySQL la columna
# TIMESTAMP y NOW() dependen de la zona de la sesión: se fija en UTC al conectar.
if engine.dialect.name == "mysql":
    @event.listens_for(engine, "connect")
    def _sesion_en_utc(conexion_dbapi, _registro):
        cursor = conexion_dbapi.cursor()
        cursor.execute("SET time_zone = '+00:00'")
        cursor.close()

# Crear las sesiones para consultar la base de datos
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base utilizada por los modelos de SQLAlchemy
Base = declarative_base()


# Proporcionar una sesión a cada petición de FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
