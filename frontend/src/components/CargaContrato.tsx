import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import axios from "axios";
import { api, getErrorMessage } from "../api/client";
import { useAuth } from "../context/AuthContext";
import CampoContexto from "./CampoContexto";
import type { CargaContratoRespuesta, OpcionCatalogo } from "../types";

export default function CargaContrato() {
  const navigate = useNavigate();
  const { usuario } = useAuth();
  const [tipos, setTipos] = useState<OpcionCatalogo[]>([]);
  const [roles, setRoles] = useState<OpcionCatalogo[]>([]);
  const [tipo, setTipo] = useState("");
  const [rol, setRol] = useState(usuario?.rol === "PYME" ? "CONTRATANTE" : "PRESTADOR");
  const [contexto, setContexto] = useState("");
  const [analizar, setAnalizar] = useState(true);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState("");
  const [duplicado, setDuplicado] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<OpcionCatalogo[]>("/contratos/tipos"),
      api.get<OpcionCatalogo[]>("/contratos/roles-parte"),
    ])
      .then(([t, r]) => {
        setTipos(t.data);
        setRoles(r.data);
      })
      .catch((e) => setError(getErrorMessage(e)));
  }, []);

  async function subir(e: FormEvent) {
    e.preventDefault();
    if (!archivo) return;
    setError("");
    setDuplicado(null);
    setSubiendo(true);
    const datos = new FormData();
    datos.append("archivo", archivo);
    if (tipo) datos.append("tipo_contrato", tipo);
    if (rol) datos.append("rol_parte", rol);
    if (contexto.trim()) datos.append("contexto", contexto.trim());
    try {
      const { data } = await api.post<CargaContratoRespuesta>("/contratos", datos);
      navigate(`/contratos/${data.contrato.id_contrato}${analizar ? "?analizar=1" : ""}`);
    } catch (err) {
      setError(getErrorMessage(err));
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        setDuplicado(err.response.data?.detail?.id_contrato ?? null);
      }
    } finally {
      setSubiendo(false);
    }
  }

  return (
    <form onSubmit={subir} className="space-y-4 rounded-xl bg-white p-5 shadow">
      <div>
        <h2 className="font-semibold text-slate-800">Cargar un contrato</h2>
        <p className="text-sm text-slate-500">
          PDF digital o escaneado, en castellano, de hasta 15 páginas. Los escaneados se leen con OCR.
        </p>
      </div>
      {error && (
        <p className="rounded bg-red-50 p-2 text-sm text-red-700">
          {error}
          {duplicado && (
            <button type="button" onClick={() => navigate(`/contratos/${duplicado}`)}
              className="ml-2 font-medium underline">
              Ver el contrato cargado
            </button>
          )}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <select id="contrato_tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
          <option value="">Tipo de contrato (opcional)</option>
          {tipos.map((t) => <option key={t.codigo} value={t.codigo}>{t.nombre}</option>)}
        </select>
        <input id="contrato_archivo" type="file" accept="application/pdf,.pdf" required
          onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
          className="min-w-0 flex-1 text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-slate-200" />
      </div>

      <CampoContexto roles={roles} rol={rol} onRol={setRol} contexto={contexto} onContexto={setContexto} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={analizar} onChange={(e) => setAnalizar(e.target.checked)} />
          Analizar riesgos al terminar la carga
        </label>
        <button disabled={subiendo || !archivo}
          className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {subiendo ? "Leyendo el contrato..." : analizar ? "Cargar y analizar" : "Cargar contrato"}
        </button>
      </div>
      {subiendo && (
        <p className="text-xs text-slate-500">
          Un contrato escaneado puede tardar algunos segundos por página mientras se aplica OCR.
        </p>
      )}
    </form>
  );
}