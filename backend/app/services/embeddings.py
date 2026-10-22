"""Generación de embeddings con la API de OpenAI."""

import openai

from app.config import settings

TAMANIO_LOTE = 100  # textos por solicitud a la API


class ErrorEmbeddings(Exception):
    """No se pudieron generar los embeddings."""


_cliente: openai.OpenAI | None = None


def _obtener_cliente() -> openai.OpenAI:
    global _cliente
    if not settings.openai_api_key:
        raise ErrorEmbeddings("Falta configurar OPENAI_API_KEY en el archivo .env")
    if _cliente is None:
        _cliente = openai.OpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=3)
    return _cliente


def generar_embeddings(textos: list[str], modelo: str, dimension: int) -> list[list[float]]:
    cliente = _obtener_cliente()
    vectores: list[list[float]] = []
    try:
        for inicio in range(0, len(textos), TAMANIO_LOTE):
            lote = textos[inicio:inicio + TAMANIO_LOTE]
            respuesta = cliente.embeddings.create(model=modelo, input=lote, dimensions=dimension)
            vectores.extend(d.embedding for d in sorted(respuesta.data, key=lambda d: d.index))
    except openai.AuthenticationError as error:
        raise ErrorEmbeddings("La clave OPENAI_API_KEY no es válida") from error
    except openai.RateLimitError as error:
        raise ErrorEmbeddings("Se superó el límite de uso o no hay saldo en la cuenta de OpenAI") from error
    except openai.APIConnectionError as error:
        raise ErrorEmbeddings("No se pudo conectar con OpenAI. Revise su conexión a internet") from error
    except openai.OpenAIError as error:
        raise ErrorEmbeddings(f"OpenAI rechazó la solicitud de embeddings: {type(error).__name__}") from error
    return vectores