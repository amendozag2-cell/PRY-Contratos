from fastapi import FastAPI
from sqlalchemy import text
from app.db import engine

app = FastAPI(title="Detección de Riesgos Contractuales API", version="0.1.0")

@app.get("/health")
def health():
    with engine.connect() as conn:
        pgvector = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ).scalar()
    return {"status": "ok", "database": "connected", "pgvector": pgvector}