from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routers import administracion, autenticacion, contratos, corpus

app = FastAPI(title="Detección de Riesgos Contractuales API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(autenticacion.router)
app.include_router(contratos.router)
app.include_router(administracion.router)
app.include_router(corpus.router)


@app.get("/health", tags=["Sistema"])
def health():
    with engine.connect() as conn:
        pgvector = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ).scalar()
    return {"status": "ok", "database": "connected", "pgvector": pgvector}