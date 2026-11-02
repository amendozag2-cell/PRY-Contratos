"""Verificación de las condiciones acordadas: ¿el contrato recoge lo que el usuario dice que pactó?

1. El LLM separa el texto libre del usuario en condiciones concretas.
2. Cada condición se compara (coseno) con los embeddings de las cláusulas del contrato.
3. El LLM decide si las cláusulas más parecidas la cubren, la cubren a medias,
   la contradicen o no la mencionan.
"""

import math

from app.models import Clausula

MAX_CONDICIONES = 15
CLAUSULAS_POR_CONDICION = 4
MAX_CARACTERES_CANDIDATA = 2000

INSTRUCCIONES_EXTRACCION = """Ayudas a revisar contratos. El usuario describe con sus palabras lo que acordó con la otra parte. Separa esa descripción en condiciones concretas y verificables: actividad o servicio, lugar, horario, días, exclusiones, actividades adicionales, pagos, plazos, entregables, duración, etc.

Reglas:
1. Una condición por elemento, redactada en una oración breve y autónoma en español (que se entienda sin leer las demás).
2. No agregues condiciones que el usuario no mencionó ni opiniones sobre ellas.
3. Máximo {maximo} condiciones. Si el texto no contiene condiciones, devuelve la lista vacía."""

INSTRUCCIONES_VERIFICACION = """Eres un analista jurídico que compara lo que el usuario acordó con lo que dice el contrato. Recibirás UNA condición acordada y las cláusulas del contrato más relacionadas con ella, cada una con su número.

Responde con una de estas coberturas:
- CUBIERTA: alguna cláusula recoge la condición de forma clara y completa.
- PARCIAL: la recoge de forma incompleta, ambigua o con excepciones que la debilitan (por ejemplo "salvo que la administración lo requiera").
- CONTRADICHA: alguna cláusula establece lo contrario.
- AUSENTE: ninguna de las cláusulas la menciona.

En "clausula" pon el número de la cláusula que trata la condición (la más pertinente) o null si es AUSENTE. Explica en máximo dos oraciones, en español sencillo; si es PARCIAL, CONTRADICHA o AUSENTE, sugiere qué conviene agregar o corregir en el contrato. Esta revisión es una ayuda y no constituye asesoría legal."""


def coseno(a: list[float], b: list[float]) -> float:
    producto = sum(x * y for x, y in zip(a, b))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return producto / norma if norma else 0.0


def clausulas_candidatas(vector: list[float], clausulas: list[Clausula],
                         vectores: list[list[float]], cantidad: int = CLAUSULAS_POR_CONDICION) -> list[Clausula]:
    """Cláusulas del contrato más parecidas a una condición, en orden del documento."""
    puntajes = sorted(
        ((coseno(vector, v), c) for c, v in zip(clausulas, vectores, strict=True)),
        key=lambda par: par[0], reverse=True,
    )
    elegidas = [c for _, c in puntajes[:cantidad]]
    return sorted(elegidas, key=lambda c: c.numero_orden)


def mensaje_extraccion(perfil: str, contexto: str) -> str:
    return f"Perfil del usuario: {perfil}\n\nLO QUE EL USUARIO DICE QUE ACORDARON:\n{contexto}"


def mensaje_verificacion(perfil: str, condicion: str, candidatas: list[Clausula]) -> str:
    partes = [
        f"Perfil del usuario: {perfil}",
        "",
        f"CONDICIÓN ACORDADA: {condicion}",
        "",
        "CLÁUSULAS DEL CONTRATO:",
    ]
    for c in candidatas:
        titulo = c.titulo or "Encabezado y comparecientes"
        partes.append(f"[{c.numero_orden}] {titulo}")
        partes.append(c.contenido[:MAX_CARACTERES_CANDIDATA])
    return "\n".join(partes)