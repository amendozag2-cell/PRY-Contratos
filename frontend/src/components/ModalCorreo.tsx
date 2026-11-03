import { useEffect, useRef, useState } from "react";
import { api, getErrorMessage } from "../api/client";
import type { CodigoTonoCorreo, CorreoNegociacion } from "../types";

interface Props {
  abierto: boolean;
  idContrato: number;
  /** Hay condiciones acordadas que el contrato no recoge del todo. */
  hayCondiciones: boolean;
  onCerrar: () => void;
}

/** Redacta el correo para pedir a la otra parte los cambios del contrato. El usuario lo copia y lo envía. */
export default function ModalCorreo({ abierto, idContrato, hayCondiciones, onCerrar }: Props) {
  const [destinatario, setDestinatario] = useState("");
  const [tono, setTono] = useState<CodigoTonoCorreo>("FORMAL");
  const [advertencias, setAdvertencias] = useState(false);
  const [condiciones, setCondiciones] = useState(true);
  const [redactando, setRedactando] = useState(false);
  const [correo, setCorreo] = useState<CorreoNegociacion | null>(null);
  const [anteriores, setAnteriores] = useState<CorreoNegociacion[]>([]);
  const [copiado, setCopiado] = useState("");
  const [error, setError] = useState("");
  const cerrar = useRef(onCerrar);
  useEffect(() => {
    cerrar.current = onCerrar;
  });

  useEffect(() => {
    if (!abierto) return;
    setError("");
    api.get<CorreoNegociacion[]>(`/contratos/${idContrato}/correos`)
      .then((r) => {
        setAnteriores(r.data);
        setCorreo((actual) => actual ?? r.data[0] ?? null);
      })
      .catch(() => {});
  }, [abierto, idContrato]);

  useEffect(() => {
    if (!abierto) return;
    function alPresionar(e: KeyboardEvent) {
      if (e.key === "Escape" && !redactando) cerrar.current();
    }
    window.addEventListener("keydown", alPresionar);
    return () => window.removeEventListener("keydown", alPresionar);
  }, [abierto, redactando]);

  if (!abierto) return null;

  async function redactar() {
    setError("");
    setRedactando(true);
    try {
      const { data } = await api.post<CorreoNegociacion>(`/contratos/${idContrato}/correos`, {
        destinatario: destinatario.trim() || null,
        tono,
        incluir_advertencias: advertencias,
        incluir_condiciones: condiciones,
      });
      setCorreo(data);
      setAnteriores((lista) => [data, ...lista]);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setRedactando(false);
    }
  }

  async function copiar(texto: string, que: string) {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(que);
      setTimeout(() => setCopiado(""), 2000);
    } catch {
      setError("No se pudo copiar. Selecciona el texto y cópialo manualmente.");
    }
  }

  const mailto = correo
    ? `mailto:?subject=${encodeURIComponent(correo.asunto)}&body=${encodeURIComponent(correo.cuerpo)}`
    : "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !redactando) onCerrar(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="correo-titulo"
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 id="correo-titulo" className="text-lg font-semibold text-slate-800">Correo para negociar el contrato</h2>
          <button onClick={onCerrar} disabled={redactando} aria-label="Cerrar"
            className="rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100">✕</button>
        </div>

        <div className="space-y-5 overflow-y-auto px-6 py-5">
          {/* Opciones */}
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Para (opcional)</span>
              <input value={destinatario} onChange={(e) => setDestinatario(e.target.value)} maxLength={150}
                placeholder="Ej.: Ing. Carlos Pérez, gerente de Comercial XYZ"
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none" />
            </label>
            <fieldset className="text-sm">
              <legend className="font-medium text-slate-700">Tono</legend>
              <div className="mt-1 flex gap-2">
                {(["FORMAL", "CORDIAL"] as const).map((t) => (
                  <button key={t} type="button" onClick={() => setTono(t)}
                    className={`flex-1 rounded-lg border px-3 py-2 ${tono === t ? "border-blue-600 bg-blue-50 text-blue-800" : "border-slate-300 hover:bg-slate-50"}`}>
                    {t === "FORMAL" ? "Formal" : "Cordial"}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>
          <div className="space-y-2 text-sm text-slate-700">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={advertencias} onChange={(e) => setAdvertencias(e.target.checked)} />
              Incluir también las cláusulas con advertencia (riesgo medio)
            </label>
            {hayCondiciones && (
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={condiciones} onChange={(e) => setCondiciones(e.target.checked)} />
                Pedir que se incluyan las condiciones acordadas que faltan en el contrato
              </label>
            )}
            <p className="text-xs text-slate-500">
              Se piden los cambios de las cláusulas de riesgo alto con su contrapropuesta (o el texto acordado).
              Las que la otra parte ya rechazó no se vuelven a pedir.
            </p>
          </div>
          <button onClick={redactar} disabled={redactando}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60">
            {redactando ? "Redactando correo..." : correo ? "Redactar otra versión" : "Redactar correo"}
          </button>
          {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

          {/* Resultado */}
          {correo && (
            <div className="space-y-3 rounded-xl border bg-slate-50 p-4">
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Asunto</span>
                  <button onClick={() => copiar(correo.asunto, "asunto")} className="text-xs text-blue-700 hover:underline">
                    {copiado === "asunto" ? "¡Copiado!" : "Copiar asunto"}
                  </button>
                </div>
                <p className="mt-1 font-medium text-slate-800">{correo.asunto}</p>
              </div>
              <div>
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Mensaje</span>
                <p className="mt-1 max-h-80 overflow-y-auto whitespace-pre-line rounded-lg bg-white p-3 text-sm text-slate-800">
                  {correo.cuerpo}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-sm">
                <button onClick={() => copiar(correo.cuerpo, "cuerpo")}
                  className="rounded-lg bg-slate-800 px-4 py-1.5 font-medium text-white hover:bg-slate-900">
                  {copiado === "cuerpo" ? "¡Copiado!" : "Copiar mensaje"}
                </button>
                <a href={mailto} className="rounded-lg border border-slate-300 bg-white px-4 py-1.5 hover:bg-slate-50">
                  Abrir en mi correo
                </a>
              </div>
              <p className="text-xs text-slate-500">
                Revisa y ajusta el texto antes de enviarlo. Es una ayuda para negociar y no constituye asesoría legal.
              </p>
            </div>
          )}

          {/* Historial */}
          {anteriores.length > 1 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-slate-600">Correos anteriores ({anteriores.length})</summary>
              <ul className="mt-2 divide-y rounded-lg border">
                {anteriores.map((c) => (
                  <li key={c.id_correo}>
                    <button onClick={() => setCorreo(c)}
                      className={`w-full px-3 py-2 text-left hover:bg-slate-50 ${correo?.id_correo === c.id_correo ? "bg-blue-50" : ""}`}>
                      <span className="block truncate font-medium text-slate-800">{c.asunto}</span>
                      <span className="text-xs text-slate-500">
                        {new Date(c.fecha_creacion).toLocaleString("es-EC")} · {c.tono.nombre}
                        {c.destinatario && ` · ${c.destinatario}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}