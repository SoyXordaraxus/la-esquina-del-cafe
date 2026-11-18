from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import auth_tableros, ventas

app = FastAPI(title="La Esquina del Café API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_tableros.router)
app.include_router(ventas.router)

@app.get("/")
def health_check():
    return {"status": "ok", "mensaje": "Servidor activo"}