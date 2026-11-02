import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { api, getErrorMessage } from "../api/client";
import CampoContexto from "../components/CampoContexto";
import VisorContrato from "../components/VisorContrato";
import { COLOR_NEUTRO, conAlfa } from "../utils/colores";
import type { ClausulaContrato, CodigoNivel, ContratoDetalle, OpcionCatalogo } from "../types";

function Insignia({ clausula }: { clausula: ClausulaContrato }) {
  const nivel = clausula.nivel_riesgo;
  if (!nivel) return null;
  return (
    <span className="rounded-full px-2 py-0.5 text-xs font-semibold text-white" style={{ backgroundColor: nivel.color_hex }}>
      {nivel.nombre}
    </span>
  );
}

export default function ContratoPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [contrato, setContrato] = useState<ContratoDetalle | null>(null);
  const [error, setError] = useState("");
  const [pagina, setPagina] = useState(1);
  const [seleccionada, setSeleccionada] = useState<number | null>(null);
  const [filtro, setFiltro] = useState<CodigoNivel | "">("");
  const [analizando, setAnalizando] = useState(false);
  const refs = useRef<Record<number, HTMLLIElement | null>>({});
  const [params, setParams] = useSearchParams();
  const autoAnalisis = useRef(false);
  // Edición del contexto (papel en el contrato y lo acordado)
  const [roles, setRoles] = useState<OpcionCatalogo[]>([]);
  const [editando, setEditando] = useState(false);
  const [rolEdicion, setRolEdicion] = useState("");
  const [contextoEdicion, setContextoEdicion] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [contextoPendiente, setContextoPendiente] = useState(false);

  useEffect(() => {
    api.get<ContratoDetalle>(`/contratos/${id}`)
      .then((r) => setContrato(r.data))
      .catch((e) => setError(getErrorMessage(e)));
  }, [id]);

  useEffect(() => {
    api.get<OpcionCatalogo[]>("/contratos/roles-parte").then((r) => setRoles(r.data)).catch(() => {});
  }, []);

  // Si viene de "Cargar y analizar", el análisis empieza solo (una vez)
  useEffect(() => {
    if (!contrato || autoAnalisis.current || params.get("analizar") !== "1") return;
    autoAnalisis.current = true;
    setParams({}, { replace: true });
    if (contrato.estado_analisis !== "ANALIZADO") void analizar();
  }, [contrato, params]); // eslint-disable-line react-hooks/exhaustive-deps

  async function analizar() {
    if (!contrato) return;
    setError("");
    setAnalizando(true);
    try {
      const { data } = await api.post<ContratoDetalle>(`/contratos/${contrato.id_contrato}/analizar`);
      setContrato(data);
      setFiltro("");
      setContextoPendiente(false);
    } catch (e) {
      setError(getErrorMessage(e));
      api.get<ContratoDetalle>(`/contratos/${contrato.id_contrato}`).then((r) => setContrato(r.data)).catch(() => {});
    } finally {
      setAnalizando(false);
    }
  }

  function abrirEdicion() {
    if (!contrato) return;
    setRolEdicion(contrato.rol_parte?.codigo ?? "");
    setContextoEdicion(contrato.contexto_usuario ?? "");
    setEditando(true);
  }

  async function guardarContexto() {
    if (!contrato) return;
    setError("");
    setGuardando(true);
    try {
      const { data } = await api.patch<ContratoDetalle>(`/contratos/${contrato.id_contrato}/contexto`, {
        rol_parte: rolEdicion || null,
        contexto_usuario: contextoEdicion.trim() || null,
      });
      setContrato(data);
      setEditando(false);
      setContextoPendiente(data.estado_analisis === "ANALIZADO");
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setGuardando(false);
    }
  }

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

  const analizado = contrato.estado_analisis === "ANALIZADO";
  const conteo = contrato.niveles.map((n) => ({
    ...n,
    total: contrato.clausulas.filter((c) => c.nivel_riesgo?.codigo === n.codigo).length,
  }));
  const visibles = contrato.clausulas.filter((c) => !filtro || c.nivel_riesgo?.codigo === filtro);
  const puntaje = contrato.puntaje_riesgo_global !== null ? Number(contrato.puntaje_riesgo_global) : null;
  const respaldadas = contrato.clausulas.filter((c) => c.fundamentos.length > 0).length;

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
        <div className="flex flex-wrap gap-2 text-sm">
          <button onClick={analizar} disabled={analizando}
            className="rounded-lg bg-blue-600 px-4 py-1.5 font-medium text-white hover:bg-blue-700 disabled:opacity-60">
            {analizando ? "Analizando riesgos..." : analizado ? "Volver a analizar" : "Analizar riesgos"}
          </button>
          <button onClick={inactivar} className="rounded-lg border border-red-200 px-3 py-1 text-red-700 hover:bg-red-50">
            Quitar del historial
          </button>
          <Link to="/" className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-50">← Volver al panel</Link>
        </div>
      </header>

      {error && <p className="mx-6 mt-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {analizando && (
        <p className="mx-6 mt-4 rounded bg-blue-50 p-3 text-sm text-blue-800">
          Buscando normas relacionadas en el corpus legal y evaluando cada cláusula con IA. Suele tardar menos de 20 segundos.
        </p>
      )}

      {/* Contexto que dio el usuario */}
      <section className="mx-6 mt-6 rounded-xl bg-white p-5 shadow">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-slate-800">Tu contexto</h2>
          {!editando && (
            <button onClick={abrirEdicion} className="rounded-lg border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50">
              Editar
            </button>
          )}
        </div>
        {editando ? (
          <div className="space-y-3">
            <CampoContexto roles={roles} rol={rolEdicion} onRol={setRolEdicion}
              contexto={contextoEdicion} onContexto={setContextoEdicion} />
            <div className="flex gap-2 text-sm">
              <button onClick={guardarContexto} disabled={guardando}
                className="rounded-lg bg-blue-600 px-4 py-1.5 font-medium text-white hover:bg-blue-700 disabled:opacity-60">
                {guardando ? "Guardando..." : "Guardar"}
              </button>
              <button onClick={() => setEditando(false)} className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-50">
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-1 text-sm">
            <p className="text-slate-600">
              Papel: <span className="font-medium text-slate-800">{contrato.rol_parte?.nombre ?? "No indicado"}</span>
            </p>
            {contrato.contexto_usuario ? (
              <p className="whitespace-pre-line text-slate-700">{contrato.contexto_usuario}</p>
            ) : (
              <p className="text-slate-500">
                No indicaste lo que acordaron. Si lo describes, el sistema revisa si cada condición está en el contrato.
              </p>
            )}
            {contextoPendiente && (
              <p className="rounded bg-amber-50 p-2 text-amber-800">
                Guardado. Pulsa "Volver a analizar" para aplicar el nuevo contexto.
              </p>
            )}
          </div>
        )}
      </section>

      {/* Resumen del diagnóstico */}
      {analizado && (
        <section className="mx-6 mt-6 grid gap-4 rounded-xl bg-white p-5 shadow md:grid-cols-[auto_minmax(0,1fr)]">
          <div className="flex flex-col items-center justify-center gap-1 px-4">
            <span className="text-xs uppercase tracking-wide text-slate-500">Puntaje de riesgo</span>
            <span className="text-4xl font-bold tabular-nums text-slate-800">{puntaje?.toFixed(0) ?? "—"}</span>
            <span className="text-xs text-slate-500">de 100</span>
            <span className="mt-2 text-xs text-slate-500 tabular-nums" title="Cláusulas evaluadas con normas del corpus legal">
              {respaldadas} de {contrato.clausulas.length} con norma
            </span>
          </div>
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap gap-2">
              <button onClick={() => setFiltro("")}
                className={`rounded-full border px-3 py-1 text-sm ${filtro === "" ? "border-slate-800 bg-slate-800 text-white" : "border-slate-300"}`}>
                Todas · {contrato.clausulas.length}
              </button>
              {conteo.map((n) => (
                <button key={n.codigo} onClick={() => setFiltro(filtro === n.codigo ? "" : n.codigo)}
                  className="flex items-center gap-2 rounded-full border px-3 py-1 text-sm"
                  style={filtro === n.codigo
                    ? { backgroundColor: n.color_hex, borderColor: n.color_hex, color: "white" }
                    : { borderColor: conAlfa(n.color_hex, 0.5) }}>
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: filtro === n.codigo ? "white" : n.color_hex }} />
                  {n.nombre} · <span className="tabular-nums">{n.total}</span>
                </button>
              ))}
            </div>
            <p className="text-sm text-slate-700">{contrato.resumen}</p>
            <p className="text-xs text-slate-500 tabular-nums">
              Analizado el {contrato.fecha_analisis && new Date(contrato.fecha_analisis).toLocaleString("es-EC")}
              {contrato.tiempo_procesamiento_ms !== null && ` en ${(contrato.tiempo_procesamiento_ms / 1000).toFixed(1)} s`}.
              Este diagnóstico es una ayuda y no reemplaza la asesoría de un abogado.
            </p>
          </div>
        </section>
      )}

      {/* Lo que acordaste vs. lo que dice el contrato */}
      {analizado && contrato.condiciones.length > 0 && (
        <section className="mx-6 mt-6 rounded-xl bg-white shadow">
          <h2 className="border-b p-4 font-semibold text-slate-800">Lo que acordaste vs. lo que dice el contrato</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="p-3">Condición acordada</th>
                  <th className="p-3">Resultado</th>
                  <th className="p-3">Dónde</th>
                  <th className="p-3">Explicación</th>
                </tr>
              </thead>
              <tbody>
                {contrato.condiciones.map((k) => (
                  <tr key={k.numero_orden} className="border-t align-top">
                    <td className="p-3 font-medium text-slate-800">{k.descripcion}</td>
                    <td className="p-3">
                      <span className="whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold text-white"
                        style={{ backgroundColor: k.cobertura.color_hex }}>
                        {k.cobertura.nombre}
                      </span>
                    </td>
                    <td className="p-3 whitespace-nowrap">
                      {k.id_clausula !== null ? (
                        <button onClick={() => seleccionar(k.id_clausula!)} className="text-blue-700 hover:underline"
                          title={k.titulo_clausula ?? undefined}>
                          Cláusula #{k.numero_clausula}
                        </button>
                      ) : "—"}
                    </td>
                    <td className="p-3 text-slate-700">{k.explicacion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <main className="grid gap-6 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        {/* Cláusulas */}
        <section className="min-w-0 rounded-xl bg-white shadow">
          <h2 className="border-b p-4 font-semibold text-slate-800">
            {analizado ? "Diagnóstico por cláusula" : "Cláusulas detectadas"}
          </h2>
          <ol className="max-h-[75vh] divide-y overflow-y-auto">
            {visibles.length === 0 && <li className="p-6 text-center text-sm text-slate-500">No hay cláusulas en este nivel.</li>}
            {visibles.map((c) => {
              const activa = seleccionada === c.id_clausula;
              const color = c.nivel_riesgo?.color_hex ?? COLOR_NEUTRO;
              return (
                <li key={c.id_clausula} ref={(el) => { refs.current[c.id_clausula] = el; }}
                  className="border-l-4" style={{ borderLeftColor: c.nivel_riesgo ? color : "transparent" }}>
                  <button onClick={() => seleccionar(c.id_clausula)}
                    className={`w-full p-4 text-left hover:bg-slate-50 ${activa ? "bg-slate-50" : ""}`}>
                    <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span className="font-mono">#{c.numero_orden}</span>
                      <span>pág. {c.numero_pagina}</span>
                      <Insignia clausula={c} />
                      {c.categoria_riesgo && (
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">{c.categoria_riesgo.nombre}</span>
                      )}
                      {c.nivel_riesgo && (c.fundamentos.length > 0 ? (
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">Con norma</span>
                      ) : (
                        <span className="rounded border border-dashed border-slate-300 px-1.5 py-0.5 text-slate-500"
                          title="No hay normas del corpus sobre este tema">
                          Criterio general
                        </span>
                      ))}
                    </div>
                    <p className="font-medium text-slate-800">{c.titulo ?? "Encabezado y comparecientes"}</p>
                    {c.explicacion && <p className="mt-1 text-sm text-slate-700">{c.explicacion}</p>}
                    {activa && (
                      <p className="mt-2 whitespace-pre-line rounded bg-slate-50 p-2 text-sm text-slate-600">{c.contenido}</p>
                    )}
                  </button>
                  {activa && c.nivel_riesgo && c.fundamentos.length === 0 && (
                    <p className="mx-4 mb-4 rounded bg-slate-50 p-2 text-xs text-slate-600">
                      El corpus legal no tiene normas sobre este tema, así que la cláusula se evaluó con criterios
                      generales de equidad y redacción. El administrador puede cargar la ley correspondiente.
                    </p>
                  )}
                  {activa && c.fundamentos.length > 0 && (
                    <div className="space-y-2 px-4 pb-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Normas consultadas</p>
                      {c.fundamentos.map((f) => (
                        <details key={f.id_fragmento} className="rounded border bg-white p-2 text-sm">
                          <summary className="cursor-pointer text-slate-700">
                            {f.titulo_documento}{f.articulo_referencia && `, ${f.articulo_referencia}`}
                            <span className="ml-2 text-xs text-slate-400 tabular-nums">similitud {(f.similitud * 100).toFixed(0)} %</span>
                          </summary>
                          <p className="mt-2 whitespace-pre-line text-slate-600">{f.contenido}</p>
                        </details>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        </section>

        {/* Visor del contrato con las cláusulas coloreadas según el semáforo */}
        <VisorContrato contrato={contrato} pagina={pagina} onPagina={setPagina}
          seleccionada={seleccionada} onSeleccionar={seleccionar} filtro={filtro} />
      </main>
    </div>
  );
}