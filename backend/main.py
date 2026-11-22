from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import SessionLocal
from routes import auth_tableros, ventas, almacen, catalogos, reportes_admin

app = FastAPI(title="La Esquina del Café - API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_tableros.router)
app.include_router(ventas.router)
app.include_router(almacen.router)
app.include_router(catalogos.router)
app.include_router(reportes_admin.router)


# RF 21: Respaldo automático al cerrarse el servidor
@app.on_event("shutdown")
def respaldo_al_cerrar():
    db = SessionLocal()
    try:
        reportes_admin.ejecutar_respaldo_sql(tipo="auto_cierre", id_usuario=1, db=db)
    except Exception:
        pass
    finally:
        db.close()


# Servir frontend estático desde http://127.0.0.1:8000/login.html (Fig. 6)
ruta_frontend = Path(__file__).resolve().parent.parent / "frontend"
if ruta_frontend.exists():
    app.mount("/", StaticFiles(directory=str(ruta_frontend), html=True), name="frontend")