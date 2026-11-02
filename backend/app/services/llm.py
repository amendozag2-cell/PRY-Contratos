"""Llamadas al modelo de lenguaje (OpenAI) con salida estructurada en JSON."""

from typing import Literal, TypeVar

import openai
from pydantic import BaseModel, Field

from app.config import settings


class ErrorLLM(Exception):
    """El modelo de lenguaje no pudo responder."""


# ------------------------------------------------- formatos de respuesta
class DiagnosticoClausula(BaseModel):
    """Semáforo de una cláusula."""

    nivel: Literal["ALTO", "MEDIO", "BAJO"]
    categoria: str = Field(description="Código de la categoría de riesgo o NINGUNA")
    explicacion: str = Field(description="Máximo tres oraciones en español sencillo")
    fundamentos: list[int] = Field(description="Números de los fragmentos del contexto que fundamentan la decisión")


class CondicionesExtraidas(BaseModel):
    """Condiciones que el usuario dice haber acordado, separadas una por una."""

    condiciones: list[str] = Field(description="Cada condición en una oración breve y autónoma")


class VerificacionCondicion(BaseModel):
    """Si el contrato recoge una condición acordada."""

    cobertura: Literal["CUBIERTA", "PARCIAL", "CONTRADICHA", "AUSENTE"]
    clausula: int | None = Field(description="Número de la cláusula que trata la condición, o null si ninguna")
    explicacion: str = Field(description="Máximo dos oraciones en español sencillo")


Formato = TypeVar("Formato", bound=BaseModel)

_cliente: openai.OpenAI | None = None


def _obtener_cliente() -> openai.OpenAI:
    global _cliente
    if not settings.openai_api_key:
        raise ErrorLLM("Falta configurar OPENAI_API_KEY en el archivo .env")
    if _cliente is None:
        _cliente = openai.OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=2)
    return _cliente


def generar_estructurado(modelo: str, instrucciones: str, mensaje: str, formato: type[Formato]) -> Formato:
    """Envía instrucciones y mensaje al modelo y devuelve la respuesta validada con `formato`."""
    cliente = _obtener_cliente()
    try:
        respuesta = cliente.responses.parse(
            model=modelo,
            input=[
                {"role": "system", "content": instrucciones},
                {"role": "user", "content": mensaje},
            ],
            text_format=formato,
        )
    except openai.AuthenticationError as error:
        raise ErrorLLM("La clave OPENAI_API_KEY no es válida") from error
    except openai.RateLimitError as error:
        raise ErrorLLM("Se superó el límite de uso o no hay saldo en la cuenta de OpenAI") from error
    except openai.APIConnectionError as error:
        raise ErrorLLM("No se pudo conectar con OpenAI. Revise su conexión a internet") from error
    except openai.NotFoundError as error:
        raise ErrorLLM(f"El modelo '{modelo}' no existe o no está disponible para su cuenta") from error
    except openai.OpenAIError as error:
        raise ErrorLLM(f"OpenAI rechazó la solicitud de análisis: {type(error).__name__}") from error

    if respuesta.output_parsed is None:
        raise ErrorLLM("El modelo no devolvió una respuesta válida")
    return respuesta.output_parsed


def clasificar_clausula(modelo: str, instrucciones: str, mensaje: str) -> DiagnosticoClausula:
    return generar_estructurado(modelo, instrucciones, mensaje, DiagnosticoClausula)