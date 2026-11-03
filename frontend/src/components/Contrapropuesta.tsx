import { useState } from "react";
import { api, getErrorMessage } from "../api/client";
import { conAlfa } from "../utils/colores";
import type { ClausulaContrato, CodigoEstadoContrapropuesta, ContratoDetalle } from "../types";

interface Props {
  idContrato: number;
  clausula: ClausulaContrato;
  onActualizado: (detalle: ContratoDetalle) => void;
}

/** Contrapropuesta de una cláusula riesgosa: redactarla, copiarla y registrar la respuesta de la otra parte. */
export default function Contrapropuesta({ idContrato, clausula, onActualizado }: Props) {
  const cp = clausula.contrapropuesta;
  const [procesando, setProcesando] = useState<"" | "generar" | CodigoEstadoContrapropuesta>("");
  const [editando, setEditando] = useState(false);
  const [textoAcordado, setTextoAcordado] = useState("");
  const [copiado, setCopiado] = useState(false);
  const [error, setError] = useState("");

  async function generar() {
    setError("");
    setProcesando("generar");
    try {
      const { data } = await api.post<ContratoDetalle>(`/contratos/${idContrato}/contrapropuestas`, {
        ids_clausula: [clausula.id_clausula],
      });
      setEditando(false);
      onActualizado(data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setProcesando("");
    }
  }

  async function responder(estado: Exclude<CodigoEstadoContrapropuesta, "GENERADA">) {
    setError("");
    setProcesando(estado);
    try {
      const { data } = await api.patch<ContratoDetalle>(
        `/contratos/${idContrato}/clausulas/${clausula.id_clausula}/contrapropuesta`,
        { estado, texto_acordado: estado === "MODIFICADA" ? textoAcordado : null },
      );
      setEditando(false);
      onActualizado(data);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setProcesando("");
    }
  }

  async function copiar(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      setError("No se pudo copiar. Selecciona el texto y cópialo manualmente.");
    }
  }

  const ocupado = procesando !== "";

  if (!cp) {
    return (
      <div className="mx-4 mb-4 rounded-lg border border-dashed border-blue-300 bg-blue-50/50 p-3 text-sm">
        <p className="text-slate-700">¿Quieres proponer otra redacción para esta cláusula?</p>
        <button onClick={generar} disabled={ocupado}
          className="mt-2 rounded-lg bg-blue-600 px-3 py-1.5 font-medium text-white hover:bg-blue-700 disabled:opacity-60">
          {procesando === "generar" ? "Redactando..." : "Proponer redacción"}
        </button>
        {error && <p className="mt-2 text-red-700">{error}</p>}
      </div>
    );
  }

  const texto = cp.texto_acordado ?? cp.texto_propuesto;
  const color = cp.estado.color_hex;

  return (
    <div className="mx-4 mb-4 rounded-lg border p-3 text-sm" style={{ borderColor: conAlfa(color, 0.4), backgroundColor: conAlfa(color, 0.04) }}>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {cp.texto_acordado ? "Texto acordado" : "Contrapropuesta"}
        </p>
        <span className="rounded-full px-2 py-0.5 text-xs font-semibold text-white" style={{ backgroundColor: color }}>
          {cp.estado.nombre}
        </span>
      </div>

      <p className="whitespace-pre-line rounded bg-white p-2 text-slate-800">{texto}</p>
      {cp.justificacion && <p className="mt-2 text-slate-600"><span className="font-medium">Por qué: </span>{cp.justificacion}</p>}

      {editando ? (
        <div className="mt-3 space-y-2">
          <label className="block text-xs font-medium text-slate-600" htmlFor={`acordado-${clausula.id_clausula}`}>
            Escribe cómo quedó finalmente la cláusula
          </label>
          <textarea id={`acordado-${clausula.id_clausula}`} value={textoAcordado} rows={6}
            onChange={(e) => setTextoAcordado(e.target.value)} maxLength={10000}
            className="w-full rounded-lg border border-slate-300 p-2 text-sm focus:border-blue-500 focus:outline-none" />
          <div className="flex flex-wrap gap-2">
            <button onClick={() => responder("MODIFICADA")} disabled={ocupado || !textoAcordado.trim()}
              className="rounded-lg bg-teal-600 px-3 py-1.5 font-medium text-white hover:bg-teal-700 disabled:opacity-60">
              {procesando === "MODIFICADA" ? "Guardando..." : "Guardar texto acordado"}
            </button>
            <button onClick={() => setEditando(false)} disabled={ocupado}
              className="rounded-lg border border-slate-300 px-3 py-1.5 hover:bg-slate-50">
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => copiar(texto)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1 hover:bg-slate-50">
            {copiado ? "¡Copiado!" : "Copiar"}
          </button>
          <span className="mx-1 hidden self-center text-xs text-slate-400 sm:inline">La otra parte:</span>
          <button onClick={() => responder("ACEPTADA")} disabled={ocupado || cp.estado.codigo === "ACEPTADA"}
            className="rounded-lg border border-green-300 bg-white px-3 py-1 text-green-700 hover:bg-green-50 disabled:opacity-50">
            {procesando === "ACEPTADA" ? "..." : "Aceptó"}
          </button>
          <button onClick={() => { setTextoAcordado(texto); setEditando(true); }} disabled={ocupado}
            className="rounded-lg border border-teal-300 bg-white px-3 py-1 text-teal-700 hover:bg-teal-50 disabled:opacity-50">
            Aceptó con cambios
          </button>
          <button onClick={() => responder("RECHAZADA")} disabled={ocupado || cp.estado.codigo === "RECHAZADA"}
            className="rounded-lg border border-red-300 bg-white px-3 py-1 text-red-700 hover:bg-red-50 disabled:opacity-50">
            {procesando === "RECHAZADA" ? "..." : "Rechazó"}
          </button>
          <button onClick={generar} disabled={ocupado}
            className="ml-auto rounded-lg px-3 py-1 text-blue-700 hover:bg-blue-50 disabled:opacity-50"
            title="Redactar una nueva propuesta (reemplaza la actual)">
            {procesando === "generar" ? "Redactando..." : "Regenerar"}
          </button>
        </div>
      )}
      {error && <p className="mt-2 text-red-700">{error}</p>}
    </div>
  );
}