from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import auth_tableros, ventas, almacen  # , catalogos, reportes_admin

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
# app.include_router(catalogos.router)
# app.include_router(reportes_admin.router)