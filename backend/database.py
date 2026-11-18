
import os

from sqlalchemy import create_engine
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
