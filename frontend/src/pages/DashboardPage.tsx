import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, getErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import CargaContrato from "../components/CargaContrato";
import type { Contrato, EstadoAnalisis, Rol } from "../types";

const etiquetaRol: Record<Rol, string> = {
  FREELANCER: "Freelancer",
  PYME: "PYME",
  ADMINISTRADOR: "Administrador",
};

const etiquetaEstado: Record<EstadoAnalisis, string> = {
  CARGADO: "Cargado",
  PROCESANDO: "Procesando",
  ANALIZADO: "Analizado",
  ERROR: "Error",
};

/** Color del puntaje global: 0-33 bajo, 34-66 medio, 67-100 alto. */
function colorPuntaje(puntaje: number) {
  if (puntaje >= 67) return "bg-red-100 text-red-700";
  if (puntaje >= 34) return "bg-amber-100 text-amber-800";
  return "bg-green-100 text-green-700";
}

export default function DashboardPage() {
  const { usuario, cerrarSesion } = useAuth();
  const [contratos, setContratos] = useState<Contrato[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Contrato[]>("/contratos")
      .then(({ data }) => setContratos(data))
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="flex flex-wrap items-center justify-between gap-3 bg-white px-6 py-4 shadow-sm">
        <h1 className="text-lg font-bold text-slate-800">Análisis de Riesgos Contractuales</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {usuario && (
            <span className="text-slate-600">
              {usuario.nombres} {usuario.apellidos} · {etiquetaRol[usuario.rol]}
              {usuario.nombre_empresa && ` · ${usuario.nombre_empresa}`}
            </span>
          )}
          {usuario?.rol === "ADMINISTRADOR" && (
            <>
              <Link to="/admin/corpus" className="rounded-lg bg-slate-800 px-3 py-1 text-white hover:bg-slate-700">
                Corpus legal
              </Link>
              <Link to="/admin/auditoria" className="rounded-lg bg-slate-800 px-3 py-1 text-white hover:bg-slate-700">
                Auditoría
              </Link>
            </>
          )}
          <button onClick={cerrarSesion} className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-50">
            Cerrar sesión
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-6 p-6">
        <CargaContrato />

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-slate-800">Historial de contratos</h2>
          {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

          <div className="overflow-x-auto rounded-xl bg-white shadow">
            {contratos.length === 0 ? (
              <p className="p-8 text-center text-slate-500">Aún no has cargado contratos.</p>
            ) : (
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="p-3">Archivo</th>
                    <th className="p-3">Tipo</th>
                    <th className="p-3 text-right">Páginas</th>
                    <th className="p-3 text-right">Cláusulas</th>
                    <th className="p-3">Estado</th>
                    <th className="p-3 text-right">Riesgo</th>
                    <th className="p-3">Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {contratos.map((c) => (
                    <tr key={c.id_contrato} className="border-t hover:bg-slate-50">
                      <td className="p-3">
                        <Link to={`/contratos/${c.id_contrato}`} className="font-medium text-blue-700 hover:underline">
                          {c.nombre_archivo}
                        </Link>
                        {c.es_escaneado && (
                          <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">OCR</span>
                        )}
                      </td>
                      <td className="p-3">{c.tipo_contrato ?? "—"}</td>
                      <td className="p-3 text-right tabular-nums">{c.numero_paginas ?? "—"}</td>
                      <td className="p-3 text-right tabular-nums">{c.numero_clausulas}</td>
                      <td className="p-3">{etiquetaEstado[c.estado_analisis] ?? c.estado_analisis}</td>
                      <td className="p-3 text-right tabular-nums">
                        {c.puntaje_riesgo_global !== null ? (
                          <span className={`rounded px-2 py-0.5 font-medium ${colorPuntaje(Number(c.puntaje_riesgo_global))}`}>
                            {Number(c.puntaje_riesgo_global).toFixed(0)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="p-3 tabular-nums">{new Date(c.fecha_creacion).toLocaleDateString("es-EC")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}