from fastapi import FastAPI
from sqlalchemy import text
from app.db import engine
from app.api.routes import auth

app = FastAPI(
    title="Detección de Riesgos Contractuales API",
    version="0.1.0",
    swagger_ui_parameters={"persistAuthorization": True},
)


app.include_router(auth.router)

@app.get("/health")
def health():
    with engine.connect() as conn:
        pgvector = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        ).scalar()
    return {"status": "ok", "database": "connected", "pgvector": pgvector}