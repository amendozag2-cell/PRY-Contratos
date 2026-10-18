import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.main import app

if not settings.test_database_url:
    raise RuntimeError("Define TEST_DATABASE_URL en el archivo .env para ejecutar los tests")

engine = create_engine(settings.test_database_url)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def crear_tablas():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    def override_get_db():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    with engine.begin() as conn:  # cada test empieza con la tabla vacía
        conn.execute(text("TRUNCATE users"))
