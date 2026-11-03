from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    # Valor de respaldo; el valor vigente se lee del parámetro SESION_MINUTOS_EXPIRACION
    jwt_expire_minutes: int = 60
    cors_origins: list[str] = ["http://localhost:5173"]
    zona_horaria: str = "America/Guayaquil"
    openai_api_key: str = ""
    # Carpeta donde se guardan los archivos subidos (relativa a backend/)
    directorio_archivos: str = "storage"
    max_mb_corpus: int = 20
    max_mb_contrato: int = 10
    # Firma electrónica: certificados raíz de las entidades de certificación (relativa a backend/)
    directorio_confianza: str = "certificados_confianza"
    max_kb_certificado: int = 100
    # OCR (Tesseract): carpeta tessdata con el idioma español instalado
    tessdata_prefix: str = ""
    idioma_ocr: str = "spa"
    dpi_ocr: int = 300

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


settings = Settings()