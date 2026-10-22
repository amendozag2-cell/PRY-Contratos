import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, getErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
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

      <main className="mx-auto max-w-5xl p-6">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-slate-800">Historial de contratos</h2>
          <button disabled title="Disponible en el Avance 2"
            className="rounded-lg bg-blue-600 px-4 py-2 text-white opacity-50">
            + Analizar contrato
          </button>
        </div>

        {error && <p className="mb-4 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

        <div className="overflow-x-auto rounded-xl bg-white shadow">
          {contratos.length === 0 ? (
            <p className="p-8 text-center text-slate-500">Aún no has analizado contratos.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="p-3">Archivo</th>
                  <th className="p-3">Páginas</th>
                  <th className="p-3">Estado</th>
                  <th className="p-3">Fecha</th>
                </tr>
              </thead>
              <tbody>
                {contratos.map((c) => (
                  <tr key={c.id_contrato} className="border-t">
                    <td className="p-3">{c.nombre_archivo}</td>
                    <td className="p-3">{c.numero_paginas ?? "—"}</td>
                    <td className="p-3">{etiquetaEstado[c.estado_analisis] ?? c.estado_analisis}</td>
                    <td className="p-3">{new Date(c.fecha_creacion).toLocaleDateString("es-EC")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  );
}