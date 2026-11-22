import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import func

from database import SessionLocal
from models import Usuario
from routes import auth_tableros, ventas, almacen, catalogos, reportes_admin

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:     %(name)s - %(message)s")
logging.getLogger("esquina").setLevel(logging.INFO)
logger = logging.getLogger("esquina")

app = FastAPI(title="La Esquina del Café - API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Las páginas .html no se guardan en caché (ni en el bfcache del navegador): tras cerrar
# sesión, "Atrás" debe pedirlas de nuevo y menu.js redirige a login.html.
# css/js/imágenes sí se pueden cachear.
@app.middleware("http")
async def no_cachear_html(request: Request, call_next):
    respuesta = await call_next(request)
    ruta = request.url.path
    if ruta.endswith(".html") or ruta.endswith("/"):
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


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
        admin = (
            db.query(Usuario)
            .filter(func.lower(Usuario.rol).like("%admin%"))
            .order_by(Usuario.id_usuario.asc())
            .first()
        )
        if admin is None:
            logger.warning("Respaldo al cerrar omitido: no existe ningún usuario Administrador.")
            return
        resultado = reportes_admin.generar_respaldo(db, tipo="auto_cierre", id_usuario=admin.id_usuario)
        logger.info("Respaldo al cerrar: %s", resultado["archivo"])
    except Exception:
        logger.exception("No se pudo generar el respaldo automático al cerrar el servidor")
    finally:
        db.close()


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse(url="/login.html")


# Servir frontend estático desde http://127.0.0.1:8000/login.html (Fig. 6).
# Se monta al final: un mount en "/" captura todo lo que no haya atendido un router antes.
ruta_frontend = Path(__file__).resolve().parent.parent / "frontend"
if ruta_frontend.exists():
    app.mount("/", StaticFiles(directory=str(ruta_frontend), html=True), name="frontend")