import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, getErrorMessage } from "../api/client";
import type { ContratoDetalle } from "../types";

const ANCHO_IMAGEN = 900;

export default function ContratoPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [contrato, setContrato] = useState<ContratoDetalle | null>(null);
  const [error, setError] = useState("");
  const [pagina, setPagina] = useState(1);
  const [imagen, setImagen] = useState<string | null>(null);
  const [seleccionada, setSeleccionada] = useState<number | null>(null);
  const refs = useRef<Record<number, HTMLLIElement | null>>({});

  useEffect(() => {
    api.get<ContratoDetalle>(`/contratos/${id}`)
      .then((r) => setContrato(r.data))
      .catch((e) => setError(getErrorMessage(e)));
  }, [id]);

  // La imagen se pide con el token, por eso se descarga como blob
  useEffect(() => {
    if (!contrato) return;
    let url: string | null = null;
    setImagen(null);
    api.get<Blob>(`/contratos/${contrato.id_contrato}/paginas/${pagina}/imagen`, {
      params: { ancho: ANCHO_IMAGEN },
      responseType: "blob",
    })
      .then((r) => {
        url = URL.createObjectURL(r.data);
        setImagen(url);
      })
      .catch((e) => setError(getErrorMessage(e)));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [contrato, pagina]);

  function seleccionar(idClausula: number, irAPagina = true) {
    setSeleccionada(idClausula);
    const clausula = contrato?.clausulas.find((c) => c.id_clausula === idClausula);
    if (clausula && irAPagina) setPagina(clausula.numero_pagina);
    refs.current[idClausula]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function inactivar() {
    if (!contrato) return;
    if (!window.confirm(`¿Quitar "${contrato.nombre_archivo}" de tu historial?`)) return;
    try {
      await api.patch(`/contratos/${contrato.id_contrato}/inactivar`);
      navigate("/");
    } catch (e) {
      setError(getErrorMessage(e));
    }
  }

  if (error && !contrato) {
    return (
      <div className="p-8">
        <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>
        <Link to="/" className="mt-4 inline-block text-blue-700 hover:underline">← Volver al panel</Link>
      </div>
    );
  }
  if (!contrato) return <p className="p-8 text-slate-500">Cargando contrato...</p>;

  const totalPaginas = contrato.numero_paginas ?? 1;
  const rectangulos = contrato.clausulas.flatMap((c) =>
    c.coordenadas.filter((r) => r.pagina === pagina).map((r, i) => ({ ...r, id: c.id_clausula, clave: `${c.id_clausula}-${i}` }))
  );

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="flex flex-wrap items-center justify-between gap-3 bg-white px-6 py-4 shadow-sm">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold text-slate-800">{contrato.nombre_archivo}</h1>
          <p className="text-sm text-slate-500 tabular-nums">
            {contrato.tipo_contrato ?? "Tipo no indicado"} · {contrato.numero_paginas} páginas ·{" "}
            {contrato.numero_clausulas} cláusulas
            {contrato.es_escaneado && " · leído con OCR"}
          </p>
        </div>
        <div className="flex gap-2 text-sm">
          <button onClick={inactivar} className="rounded-lg border border-red-200 px-3 py-1 text-red-700 hover:bg-red-50">
            Quitar del historial
          </button>
          <Link to="/" className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-50">← Volver al panel</Link>
        </div>
      </header>

      {error && <p className="mx-6 mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <main className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* Cláusulas detectadas */}
        <section className="min-w-0 rounded-xl bg-white shadow">
          <h2 className="border-b p-4 font-semibold text-slate-800">Cláusulas detectadas</h2>
          <ol className="max-h-[75vh] divide-y overflow-y-auto">
            {contrato.clausulas.map((c) => (
              <li key={c.id_clausula} ref={(el) => { refs.current[c.id_clausula] = el; }}>
                <button onClick={() => seleccionar(c.id_clausula)}
                  className={`w-full p-4 text-left hover:bg-slate-50 ${
                    seleccionada === c.id_clausula ? "bg-blue-50 ring-2 ring-inset ring-blue-400" : ""}`}>
                  <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
                    <span className="font-mono">#{c.numero_orden}</span>
                    <span>pág. {c.numero_pagina}</span>
                  </div>
                  <p className="font-medium text-slate-800">{c.titulo ?? "Encabezado y comparecientes"}</p>
                  <p className={`mt-1 whitespace-pre-line text-sm text-slate-600 ${
                    seleccionada === c.id_clausula ? "" : "line-clamp-3"}`}>
                    {c.contenido}
                  </p>
                </button>
              </li>
            ))}
          </ol>
        </section>

        {/* Página con las ubicaciones de las cláusulas */}
        <section className="min-w-0 space-y-3 rounded-xl bg-white p-4 shadow">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <h2 className="font-semibold text-slate-800">Ubicación en el documento</h2>
            <div className="flex items-center gap-2">
              <button disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}
                className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-40">Anterior</button>
              <span className="tabular-nums">Página {pagina} de {totalPaginas}</span>
              <button disabled={pagina >= totalPaginas} onClick={() => setPagina(pagina + 1)}
                className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-40">Siguiente</button>
            </div>
          </div>
          <div className="relative overflow-hidden rounded border bg-slate-50">
            {imagen ? (
              <img src={imagen} alt={`Página ${pagina} del contrato`} className="block w-full" />
            ) : (
              <p className="p-16 text-center text-slate-400">Cargando página...</p>
            )}
            {imagen && rectangulos.map((r) => (
              <button key={r.clave} title="Ver cláusula" onClick={() => seleccionar(r.id, false)}
                className={`absolute rounded-sm border transition-colors ${
                  seleccionada === r.id
                    ? "border-blue-600 bg-blue-500/25"
                    : "border-slate-400/40 hover:border-blue-400 hover:bg-blue-400/10"}`}
                style={{
                  left: `${r.x0 * 100}%`,
                  top: `${r.y0 * 100}%`,
                  width: `${(r.x1 - r.x0) * 100}%`,
                  height: `${(r.y1 - r.y0) * 100}%`,
                }} />
            ))}
          </div>
          <p className="text-xs text-slate-500">
            Cada recuadro es un párrafo detectado. Al elegir una cláusula se resalta su ubicación; en el
            Avance 4 los recuadros tomarán el color del semáforo de riesgo.
          </p>
        </section>
      </main>
    </div>
  );
}