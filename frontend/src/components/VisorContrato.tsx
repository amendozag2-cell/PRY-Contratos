import { useEffect, useRef, useState } from "react";
import { api, getErrorMessage } from "../api/client";
import { COLOR_NEUTRO, conAlfa } from "../utils/colores";
import type { ClausulaContrato, CodigoNivel, ContratoDetalle } from "../types";

const ANCHO_BASE = 900;
const ANCHO_MAXIMO = 2000;
const ZOOMS = [0.75, 1, 1.25, 1.5, 2];

interface Props {
  contrato: ContratoDetalle;
  pagina: number;
  onPagina: (pagina: number) => void;
  seleccionada: number | null;
  onSeleccionar: (idClausula: number, irAPagina?: boolean) => void;
  filtro: CodigoNivel | "";
}

interface Rectangulo {
  clave: string;
  clausula: ClausulaContrato;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Página del contrato con cada cláusula resaltada en el color de su nivel de riesgo. */
export default function VisorContrato({ contrato, pagina, onPagina, seleccionada, onSeleccionar, filtro }: Props) {
  const [zoom, setZoom] = useState(1);
  const [imagen, setImagen] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [hover, setHover] = useState<Rectangulo | null>(null);
  const [descargando, setDescargando] = useState(false);
  const cache = useRef<Map<string, string>>(new Map());
  const lienzo = useRef<HTMLDivElement | null>(null);

  const totalPaginas = contrato.numero_paginas ?? 1;
  const ancho = Math.min(ANCHO_MAXIMO, Math.round(ANCHO_BASE * zoom));
  const analizado = contrato.estado_analisis === "ANALIZADO";

  // Las imágenes se piden con el token (blob) y se guardan en caché por página y ancho
  useEffect(() => {
    const clave = `${contrato.id_contrato}-${pagina}-${ancho}`;
    const guardada = cache.current.get(clave);
    if (guardada) {
      setImagen(guardada);
      return;
    }
    let vigente = true;
    setImagen(null);
    setError("");
    api.get<Blob>(`/contratos/${contrato.id_contrato}/paginas/${pagina}/imagen`, {
      params: { ancho },
      responseType: "blob",
    })
      .then((r) => {
        const url = URL.createObjectURL(r.data);
        cache.current.set(clave, url);
        if (vigente) setImagen(url);
      })
      .catch((e) => vigente && setError(getErrorMessage(e)));
    return () => {
      vigente = false;
    };
  }, [contrato.id_contrato, pagina, ancho]);

  // Libera las imágenes al salir del contrato
  useEffect(() => {
    const imagenes = cache.current;
    return () => {
      imagenes.forEach((url) => URL.revokeObjectURL(url));
      imagenes.clear();
    };
  }, []);

  // Flechas del teclado para cambiar de página
  useEffect(() => {
    function alPresionar(e: KeyboardEvent) {
      const destino = e.target as HTMLElement | null;
      if (destino && ["INPUT", "TEXTAREA", "SELECT"].includes(destino.tagName)) return;
      if (e.key === "ArrowLeft" && pagina > 1) onPagina(pagina - 1);
      if (e.key === "ArrowRight" && pagina < totalPaginas) onPagina(pagina + 1);
    }
    window.addEventListener("keydown", alPresionar);
    return () => window.removeEventListener("keydown", alPresionar);
  }, [pagina, totalPaginas, onPagina]);

  // Lleva a la vista el recuadro de la cláusula seleccionada
  useEffect(() => {
    if (!imagen || seleccionada === null) return;
    lienzo.current
      ?.querySelector(`[data-clausula="${seleccionada}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
  }, [imagen, seleccionada]);

  // Nivel más alto de cada página, para el mapa de páginas
  const nivelPorPagina = new Map<number, { color: string; peso: number; nombre: string }>();
  for (const c of contrato.clausulas) {
    if (!c.nivel_riesgo) continue;
    for (const r of c.coordenadas) {
      const actual = nivelPorPagina.get(r.pagina);
      if (!actual || c.nivel_riesgo.peso > actual.peso) {
        nivelPorPagina.set(r.pagina, {
          color: c.nivel_riesgo.color_hex,
          peso: c.nivel_riesgo.peso,
          nombre: c.nivel_riesgo.nombre,
        });
      }
    }
  }

  // Cláusulas a recorrer con "anterior / siguiente": las del filtro o, sin filtro, alto y medio
  const recorrido = contrato.clausulas.filter((c) =>
    filtro ? c.nivel_riesgo?.codigo === filtro : c.nivel_riesgo && c.nivel_riesgo.codigo !== "BAJO"
  );
  const posicion = recorrido.findIndex((c) => c.id_clausula === seleccionada);

  function irARiesgo(paso: number) {
    if (recorrido.length === 0) return;
    const indice = posicion === -1
      ? (paso > 0 ? 0 : recorrido.length - 1)
      : (posicion + paso + recorrido.length) % recorrido.length;
    onSeleccionar(recorrido[indice].id_clausula, true);
  }

  async function descargar() {
    setDescargando(true);
    try {
      const { data } = await api.get<Blob>(`/contratos/${contrato.id_contrato}/archivo`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = contrato.nombre_archivo;
      enlace.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setDescargando(false);
    }
  }

  const rectangulos: Rectangulo[] = contrato.clausulas.flatMap((c) =>
    c.coordenadas
      .filter((r) => r.pagina === pagina)
      .map((r, i) => ({ ...r, clausula: c, clave: `${c.id_clausula}-${i}` }))
  );
  const indiceZoom = ZOOMS.indexOf(zoom);

  return (
    <section className="min-w-0 space-y-3 rounded-xl bg-white p-4 shadow">
      {/* Barra de herramientas */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <h2 className="font-semibold text-slate-800">Contrato</h2>
        <div className="flex flex-wrap items-center gap-2">
          {analizado && recorrido.length > 0 && (
            <div className="flex items-center gap-1">
              <button onClick={() => irARiesgo(-1)} title="Riesgo anterior"
                className="rounded-lg border border-slate-300 px-2 py-1 hover:bg-slate-50">‹</button>
              <span className="tabular-nums text-xs text-slate-600">
                {posicion === -1 ? "—" : posicion + 1} / {recorrido.length} {filtro ? "del filtro" : "riesgos"}
              </span>
              <button onClick={() => irARiesgo(1)} title="Riesgo siguiente"
                className="rounded-lg border border-slate-300 px-2 py-1 hover:bg-slate-50">›</button>
            </div>
          )}
          <div className="flex items-center gap-1">
            <button disabled={indiceZoom <= 0} onClick={() => setZoom(ZOOMS[indiceZoom - 1])} title="Alejar"
              className="rounded-lg border border-slate-300 px-2 py-1 disabled:opacity-40">−</button>
            <span className="w-12 text-center tabular-nums text-xs">{Math.round(zoom * 100)} %</span>
            <button disabled={indiceZoom >= ZOOMS.length - 1} onClick={() => setZoom(ZOOMS[indiceZoom + 1])} title="Acercar"
              className="rounded-lg border border-slate-300 px-2 py-1 disabled:opacity-40">+</button>
          </div>
          <button onClick={descargar} disabled={descargando}
            className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-50 disabled:opacity-60">
            {descargando ? "Descargando..." : "Descargar PDF"}
          </button>
        </div>
      </div>

      {/* Mapa de páginas: cada botón toma el color del riesgo más alto de esa página */}
      <nav className="flex flex-wrap items-center gap-1.5" aria-label="Páginas del contrato">
        {Array.from({ length: totalPaginas }, (_, i) => i + 1).map((n) => {
          const nivel = nivelPorPagina.get(n);
          const activa = n === pagina;
          return (
            <button key={n} onClick={() => onPagina(n)}
              title={nivel ? `Página ${n}: ${nivel.nombre}` : `Página ${n}`}
              className={`h-8 min-w-8 rounded-md border-2 px-2 text-xs font-medium tabular-nums ${activa ? "text-white" : "text-slate-700"}`}
              style={{
                borderColor: nivel?.color ?? "#CBD5E1",
                backgroundColor: activa ? (nivel?.color ?? "#334155") : nivel ? conAlfa(nivel.color, 0.12) : "white",
              }}>
              {n}
            </button>
          );
        })}
        <span className="ml-1 text-xs text-slate-500">Use ← → para cambiar de página</span>
      </nav>

      {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      {/* Página con los recuadros */}
      <div className="max-h-[80vh] overflow-auto rounded border bg-slate-100">
        <div ref={lienzo} className="relative mx-auto" style={{ width: `${zoom * 100}%` }}>
          {imagen ? (
            <img src={imagen} alt={`Página ${pagina} del contrato`} className="block w-full bg-white" />
          ) : (
            <p className="p-16 text-center text-slate-400">Cargando página...</p>
          )}
          {imagen && rectangulos.map((r) => {
            const nivel = r.clausula.nivel_riesgo;
            const color = nivel?.color_hex ?? COLOR_NEUTRO;
            const activa = seleccionada === r.clausula.id_clausula;
            const atenuada = filtro !== "" && nivel?.codigo !== filtro;
            return (
              <button key={r.clave} data-clausula={r.clausula.id_clausula}
                onClick={() => onSeleccionar(r.clausula.id_clausula, false)}
                onMouseEnter={() => setHover(r)} onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(r)} onBlur={() => setHover(null)}
                aria-label={`${nivel ? nivel.nombre + ": " : ""}${r.clausula.titulo ?? "Cláusula " + r.clausula.numero_orden}`}
                className={`absolute rounded-sm transition-opacity ${activa ? "border-[3px]" : "border-2"}`}
                style={{
                  left: `${r.x0 * 100}%`,
                  top: `${r.y0 * 100}%`,
                  width: `${(r.x1 - r.x0) * 100}%`,
                  height: `${(r.y1 - r.y0) * 100}%`,
                  borderColor: conAlfa(color, activa ? 1 : nivel ? 0.7 : 0.3),
                  backgroundColor: conAlfa(color, activa ? 0.28 : nivel ? 0.14 : 0),
                  boxShadow: activa ? `0 0 0 4px ${conAlfa(color, 0.25)}` : undefined,
                  opacity: atenuada ? 0.15 : 1,
                }} />
            );
          })}

          {/* Tarjeta al pasar el cursor */}
          {imagen && hover && (
            <div className="pointer-events-none absolute z-10 w-72 max-w-[90%] rounded-lg border bg-white p-3 text-xs shadow-lg"
              style={{
                left: `${Math.min(hover.x0 * 100, 60)}%`,
                top: hover.y1 > 0.8 ? undefined : `calc(${hover.y1 * 100}% + 6px)`,
                bottom: hover.y1 > 0.8 ? `calc(${(1 - hover.y0) * 100}% + 6px)` : undefined,
              }}>
              <div className="mb-1 flex flex-wrap items-center gap-1.5">
                {hover.clausula.nivel_riesgo && (
                  <span className="rounded-full px-2 py-0.5 font-semibold text-white"
                    style={{ backgroundColor: hover.clausula.nivel_riesgo.color_hex }}>
                    {hover.clausula.nivel_riesgo.nombre}
                  </span>
                )}
                {hover.clausula.categoria_riesgo && (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">{hover.clausula.categoria_riesgo.nombre}</span>
                )}
              </div>
              <p className="font-medium text-slate-800">{hover.clausula.titulo ?? `Cláusula ${hover.clausula.numero_orden}`}</p>
              <p className="mt-1 line-clamp-4 text-slate-600">
                {hover.clausula.explicacion ?? "Analice el contrato para ver el diagnóstico de esta cláusula."}
              </p>
              <p className="mt-1 text-slate-400">Clic para ver el detalle</p>
            </div>
          )}
        </div>
      </div>

      {/* Leyenda */}
      <div className="flex flex-wrap gap-4 text-xs text-slate-600">
        {analizado
          ? contrato.niveles.map((n) => (
              <span key={n.codigo} className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-sm border-2" style={{ borderColor: n.color_hex, backgroundColor: conAlfa(n.color_hex, 0.15) }} />
                {n.nombre}
              </span>
            ))
          : "Cada recuadro es un párrafo detectado. Analice el contrato para colorearlos según el riesgo."}
      </div>
    </section>
  );
}