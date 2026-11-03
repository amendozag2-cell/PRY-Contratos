import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, getErrorMessage } from "../api/client";
import type { DocumentoFirma } from "../types";

interface Props {
  abierto: boolean;
  idContrato: number;
  nombreDocumento: string;
  onFirmado: (documento: DocumentoFirma) => void;
  onCerrar: () => void;
}

const MOTIVO = "Acepto los términos del contrato";

/** Firma la versión final con el certificado .p12 del usuario. El certificado y la clave no se guardan. */
export default function ModalFirma({ abierto, idContrato, nombreDocumento, onFirmado, onCerrar }: Props) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [clave, setClave] = useState("");
  const [verClave, setVerClave] = useState(false);
  const [motivo, setMotivo] = useState(MOTIVO);
  const [acepto, setAcepto] = useState(false);
  const [firmando, setFirmando] = useState(false);
  const [error, setError] = useState("");
  const entrada = useRef<HTMLInputElement | null>(null);
  const cerrar = useRef(onCerrar);
  useEffect(() => {
    cerrar.current = onCerrar;
  });

  // Al cerrar se borra todo: la clave y el certificado no deben quedar en memoria del navegador
  useEffect(() => {
    if (abierto) return;
    setArchivo(null);
    setClave("");
    setVerClave(false);
    setMotivo(MOTIVO);
    setAcepto(false);
    setError("");
    if (entrada.current) entrada.current.value = "";
  }, [abierto]);

  useEffect(() => {
    if (!abierto) return;
    function alPresionar(e: KeyboardEvent) {
      if (e.key === "Escape" && !firmando) cerrar.current();
    }
    window.addEventListener("keydown", alPresionar);
    return () => window.removeEventListener("keydown", alPresionar);
  }, [abierto, firmando]);

  if (!abierto) return null;

  async function firmar(e: FormEvent) {
    e.preventDefault();
    if (!archivo || !clave || !acepto) return;
    setError("");
    setFirmando(true);
    const datos = new FormData();
    datos.append("certificado", archivo);
    datos.append("clave", clave);
    datos.append("motivo", motivo.trim() || MOTIVO);
    try {
      const { data } = await api.post<DocumentoFirma>(`/contratos/${idContrato}/firma/firmar`, datos);
      onFirmado(data);
      onCerrar();
    } catch (err) {
      setError(getErrorMessage(err));
      setClave("");
    } finally {
      setFirmando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !firmando) onCerrar(); }}>
      <form onSubmit={firmar} role="dialog" aria-modal="true" aria-labelledby="firma-titulo"
        className="w-full max-w-lg space-y-4 rounded-2xl bg-white p-6 shadow-xl">
        <div>
          <h2 id="firma-titulo" className="text-lg font-semibold text-slate-800">Firmar con mi certificado</h2>
          <p className="mt-1 truncate text-sm text-slate-500">{nombreDocumento}</p>
        </div>

        <label className="block text-sm">
          <span className="font-medium text-slate-700">Certificado de firma electrónica (.p12 o .pfx)</span>
          <input ref={entrada} type="file" accept=".p12,.pfx,application/x-pkcs12" required
            onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
            className="mt-1 block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-slate-700 hover:file:bg-slate-200" />
        </label>

        <label className="block text-sm">
          <span className="font-medium text-slate-700">Contraseña del certificado</span>
          <div className="mt-1 flex gap-2">
            <input type={verClave ? "text" : "password"} value={clave} onChange={(e) => setClave(e.target.value)}
              autoComplete="off" required maxLength={200}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none" />
            <button type="button" onClick={() => setVerClave((v) => !v)}
              className="shrink-0 rounded-lg border border-slate-300 px-3 text-slate-600 hover:bg-slate-50">
              {verClave ? "Ocultar" : "Ver"}
            </button>
          </div>
        </label>

        <label className="block text-sm">
          <span className="font-medium text-slate-700">Motivo de la firma</span>
          <input value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={255}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none" />
        </label>

        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={acepto} onChange={(e) => setAcepto(e.target.checked)} className="mt-1" />
          <span>Declaro que soy el titular del certificado, que revisé la versión final del contrato y que acepto firmarla electrónicamente.</span>
        </label>

        <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
          El certificado y su contraseña se usan solo para firmar este documento: no se guardan en el sistema.
          Solo se registran los datos públicos del certificado (titular, emisor, serie y vigencia).
        </p>

        {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" onClick={onCerrar} disabled={firmando}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60">
            Cancelar
          </button>
          <button type="submit" disabled={firmando || !archivo || !clave || !acepto}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60">
            {firmando ? "Firmando..." : "Firmar documento"}
          </button>
        </div>
      </form>
    </div>
  );
}