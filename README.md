# Aplicativo web inteligente para la detección de riesgos contractuales

Estudio de caso práctico de titulación — Ingeniería de Software, Universidad Estatal de Milagro (UNEMI).
Autores: Andy Mendoza Gavilanez y Joel Barrionuevo Sánchez.

Sistema que ayuda a **freelancers y PYMEs de Ecuador** a revisar contratos de servicios antes de firmarlos.
Combina **RAG** (recuperación de normas ecuatorianas con pgvector) y **modelos de lenguaje** (OpenAI) para
clasificar cada cláusula en un semáforo de riesgo, negociar los cambios y firmar electrónicamente la versión final.

> El sistema es una herramienta de apoyo y **no constituye asesoría legal**.

---

## Funcionalidades

| Avance | Funcionalidad |
|---|---|
| 1 | Registro e inicio de sesión (JWT), roles Freelancer / PYME / Administrador, auditoría inmutable |
| 2 | Carga de contratos PDF (digitales o escaneados con OCR) y segmentación en cláusulas con su ubicación |
| 3 | Corpus legal (RAG): carga de leyes, fragmentación por artículo y embeddings en pgvector |
| 4 | Análisis de riesgo: semáforo ALTO / MEDIO / BAJO por cláusula, con las normas citadas como fundamento |
| 4.1 | Papel del usuario (presta o contrata) y verificación de las condiciones que dice haber acordado |
| 5 | Visor del contrato con las cláusulas coloreadas según el riesgo |
| 6 | Contrapropuestas por cláusula, correo de negociación e informe PDF |
| 7 | Firma electrónica PAdES de la versión final (certificado .p12 o FirmaEC) y verificación de firmas |
| 8 | Pruebas automáticas, despliegue con Docker e integración continua |

## Arquitectura

```
Navegador ──► nginx (frontend React)  ──/api──►  FastAPI (backend)  ──►  PostgreSQL 18 + pgvector
                                                      │
                                                      ├──► OpenAI (embeddings y LLM)
                                                      ├──► PyMuPDF + Tesseract (lectura y OCR de PDF)
                                                      └──► pyHanko (firma y verificación PAdES)
```

| Capa | Tecnologías |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, React Router, Axios |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, uv |
| Base de datos | PostgreSQL 18 con pgvector (búsqueda por similitud coseno) |
| IA | OpenAI `text-embedding-3-small` (embeddings) y `gpt-5.4-mini` (clasificación y redacción) |
| Documentos | PyMuPDF (lectura, OCR con Tesseract, informe PDF), pyHanko (firma PAdES) |
| Infraestructura | Docker Compose, nginx, GitHub Actions |

## Estructura del repositorio

```
PRY-Contratos/
├── backend/
│   ├── app/
│   │   ├── routers/          Endpoints de la API (auth, contratos, firmas, admin, corpus)
│   │   ├── services/         Lógica: análisis, RAG, negociación, informe, firma...
│   │   ├── models.py         Tablas (SQLAlchemy)
│   │   └── schemas.py        Entradas y salidas de la API (Pydantic)
│   ├── migrations/versions/  Migraciones de la base de datos (Alembic)
│   ├── scripts/              Certificados de prueba y cadena de confianza
│   ├── tests/                Pruebas automáticas (pytest)
│   └── Dockerfile
├── frontend/
│   ├── src/                  Páginas y componentes React
│   ├── Dockerfile
│   └── nginx.conf
├── corpus/legal/             Textos de las leyes ecuatorianas del corpus
├── docs/                     Modelo entidad-relación
├── docker-compose.yml
└── .env.example
```

---

## Instalación para desarrollo

Requisitos: Docker Desktop, Python 3.13 con [uv](https://docs.astral.sh/uv/), Node.js 22 y, para
contratos escaneados, [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) con el idioma español.

```powershell
# 1. Variables de entorno
copy .env.example .env          # y edite los valores

# 2. Base de datos
docker compose up -d            # solo levanta PostgreSQL

# 3. Backend
cd backend
uv sync
uv run alembic upgrade head
uv run python create_admin.py   # crea el usuario administrador
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs

# 4. Frontend (otra terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

El archivo `frontend/.env` debe contener `VITE_API_URL=http://localhost:8000`.

### Corpus legal

Ingrese como administrador, abra **Corpus legal** y cargue cada archivo de `corpus/legal/`
(un documento por ley). El sistema lo divide por artículos y genera sus embeddings.

## Despliegue con Docker (sistema completo)

```powershell
docker compose --profile app up -d --build
```

| Servicio | Dirección |
|---|---|
| Aplicación web | http://localhost:8080 |
| API y documentación | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

- El backend aplica las migraciones al arrancar. El administrador se crea una sola vez con
  `docker compose exec backend python create_admin.py`.
- Los archivos subidos se guardan en `backend/storage/`, los mismos que usa el modo de desarrollo.
- Detener los servicios sin borrar datos: `docker compose --profile app down`.
- Antes de levantar el perfil `app`, detenga el backend de desarrollo, porque los dos usan el puerto 8000.

## Pruebas automáticas

Con la base de datos levantada (`docker compose up -d`):

```powershell
cd backend
uv run pytest
```

- Las pruebas usan una base **separada** (`contratos_db_test`), que se crea desde cero en cada ejecución.
  La base real no se modifica.
- OpenAI se reemplaza por respuestas simuladas: las pruebas **no gastan saldo** ni necesitan internet.
- Cubren: seguridad y roles, auditoría inmutable, segmentación, fragmentación por artículos, análisis RAG
  con normas citadas, condiciones acordadas, aislamiento entre usuarios, contrapropuestas, correo, informe PDF,
  firma PAdES (contraseña incorrecta, firma externa, manipulación del PDF, confianza) y migraciones
  (se revierten y se vuelven a aplicar).

GitHub Actions ejecuta las pruebas del backend y la compilación del frontend en cada *push*
(`.github/workflows/pruebas.yml`).

## Firma electrónica

- La versión final se firma en formato **PAdES**, con una firma incremental por cada parte.
  Las firmas anteriores siguen siendo válidas.
- El certificado `.p12` y su contraseña **solo se usan en memoria**. Se guardan únicamente los datos
  públicos del certificado: titular, emisor, serie y vigencia.
- La otra parte puede firmar con **FirmaEC**: descarga el PDF, lo firma y el usuario sube el archivo firmado.
- **Confianza:** para que el sistema reconozca a una entidad de certificación (Banco Central, Security Data,
  etc.), sus certificados raíz deben estar en `backend/certificados_confianza/`
  (`uv run python scripts/exportar_cadena_confianza.py <archivo.p12> <clave>`).
- **Pruebas sin certificado real:** `uv run python scripts/crear_certificado_prueba.py "Nombre" 0912345678 Clave123`.
  Las firmas hechas con él son íntegras pero no tienen validez legal.

## Seguridad

- Contraseñas con bcrypt y sesiones con JWT de duración configurable.
- Auditoría en `aud_auditoria`, protegida por un *trigger* que impide modificar o borrar registros.
- Cada usuario solo accede a sus propios contratos. El corpus y la auditoría son exclusivos del administrador.
- Nunca suba a GitHub el `.env`, los `.p12`/`.pfx`, `backend/storage/` ni respaldos de la base de datos.