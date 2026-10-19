import { useEffect, useState } from "react";
import { api, getErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { Contract } from "../types";

const roleLabel = { freelancer: "Freelancer", pyme: "PYME", admin: "Administrador" };
const statusLabel = {
  uploaded: "Cargado", processing: "Procesando", analyzed: "Analizado", failed: "Error",
};

export default function DashboardPage() {
  const { user, logout } = useAuth();
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Contract[]>("/contracts")
      .then(({ data }) => setContracts(data))
      .catch((err) => setError(getErrorMessage(err)));
  }, []);

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="flex items-center justify-between bg-white px-6 py-4 shadow-sm">
        <h1 className="text-lg font-bold text-slate-800">Análisis de Riesgos Contractuales</h1>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-600">
            {user?.full_name} · {user && roleLabel[user.role]}
            {user?.company_name && ` · ${user.company_name}`}
          </span>
          <button onClick={logout} className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-50">
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

        <div className="overflow-hidden rounded-xl bg-white shadow">
          {contracts.length === 0 ? (
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
                {contracts.map((c) => (
                  <tr key={c.id} className="border-t">
                    <td className="p-3">{c.original_filename}</td>
                    <td className="p-3">{c.page_count ?? "—"}</td>
                    <td className="p-3">{statusLabel[c.status]}</td>
                    <td className="p-3">{new Date(c.created_at).toLocaleDateString("es-EC")}</td>
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