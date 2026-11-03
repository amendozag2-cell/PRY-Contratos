import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { api, getErrorMessage } from "../api/client";
import ModalFirma from "./ModalFirma";
import type { DocumentoFirma, EstadoFirma } from "../types";

interface Props {
  idContrato: number;
  /** Lleva a la cláusula en el diagnóstico (para revisar un cambio acordado). */
  onIrAClausula: (idClausula: number) => void;
}

const ESTADOS: Record<EstadoFirma, { nombre: string; clase: string }> = {
  PENDIENTE: { nombre: "Pendiente de firma", clase: "bg-slate-100 text-slate-700" },
  FIRMADO_PARCIAL: { nombre: "Firmado parcialmente", clase: "bg-amber-100 text-amber-800" },
  FIRMADO_COMPLETO: { nombre: "Firmado por todas las partes", clase: "bg-green-100 text-green-800" },
  INVALIDO: { nombre: "Firma no válida", clase: "bg-red-100 text-red-800" },
};

const RESULTADOS = {
  INCLUIDA: { nombre: "Incluida", clase: "text-green-700" },
  PARCIAL: { nombre: "Con diferencias", clase: "text-amber-700" },
  NO_ENCONTRADA: { nombre: "No encontrada", clase: "text-red-700" },
} as const;

function fecha(valor: string) {
  return new Date(valor).toLocaleString("es-EC", { dateStyle: "short", timeStyle: "short" });
}

/** Firma electrónica de la versión final negociada (Avance 7). */
export default function PanelFirma({ idContrato, onIrAClausula }: Props) {
  const [documento, setDocumento] = useState<DocumentoFirma | null>(null);
  const [cargando, setCargando] = useState(true);
  const [procesando, setProcesando] = useState<"" | "carga" | "externa" | "verificar" | "descarga">("");
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [firmasRequeridas, setFirmasRequeridas] = useState(2);
  const [reemplazando, setReemplazando] = useState(false);
  const [modalFirma, setModalFirma] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const entradaFinal = useRef<HTMLInputElement | null>(null);
  const entradaExterna = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    api.get<DocumentoFirma | null>(`/contratos/${idContrato}/firma`)
      .then((r) => setDocumento(r.data))
      .catch((e) => setError(getErrorMessage(e)))
      .finally(() => setCargando(false));
  }, [idContrato]);

  async function subir(tipo: "carga" | "externa", archivo: File | undefined) {
    if (!archivo) return;
    setError("");
    setAviso("");
    setProcesando(tipo);
    const datos = new FormData();
    datos.append("archivo", archivo);
    if (tipo === "carga") datos.append("firmas_requeridas", String(firmasRequeridas));
    try {
      const ruta = tipo === "carga" ? `/contratos/${idContrato}/firma` : `/contratos/${idContrato}/firma/externa`;
      const { data } = await api.post<DocumentoFirma>(ruta, datos);
      setDocumento(data);
      setReemplazando(false);
      setAviso(tipo === "carga" ? "Versión final cargada." : "Firma externa verificada y registrada.");
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setProcesando("");
      if (entradaFinal.current) entradaFinal.current.value = "";
      if (entradaExterna.current) entradaExterna.current.value = "";
    }
  }

  async function verificar() {
    setError("");
    setAviso("");
    setProcesando("verificar");
    try {
      const { data } = await api.post<DocumentoFirma>(`/contratos/${idContrato}/firma/verificar`);
      setDocumento(data);
      setAviso(`Verificación hecha el ${fecha(new Date().toISOString())}.`);
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setProcesando("");
    }
  }

  async function descargar() {
    if (!documento) return;
    setError("");
    setProcesando("descarga");
    try {
      const { data } = await api.get<Blob>(`/contratos/${idContrato}/firma/archivo`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = `${documento.nombre_archivo.replace(/\.pdf$/i, "")} - firmado v${documento.numero_version}.pdf`;
      enlace.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(axios.isAxiosError(e) && e.response?.data instanceof Blob ? "No se pudo descargar el documento" : getErrorMessage(e));
    } finally {
      setProcesando("");
    }
  }

  async function copiarHash(hash: string) {
    try {
      await navigator.clipboard.writeText(hash);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* el usuario puede seleccionarlo manualmente */
    }
  }

  const ocupado = procesando !== "";

  const formularioCarga = (
    <div className="space-y-3 text-sm">
      <p className="text-slate-600">
        Sube el contrato final, ya con los cambios que acordaste con la otra parte, en PDF. El sistema le agrega una
        hoja de firmas y comprueba si incluye las redacciones que marcaste como aceptadas.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="font-medium text-slate-700">Firmas necesarias</span>
          <input type="number" min={1} max={10} value={firmasRequeridas}
            onChange={(e) => setFirmasRequeridas(Math.min(10, Math.max(1, Number(e.target.value) || 1)))}
            className="mt-1 block w-24 rounded-lg border border-slate-300 px-3 py-1.5 tabular-nums focus:border-blue-500 focus:outline-none" />
        </label>
        <input ref={entradaFinal} type="file" accept="application/pdf,.pdf" className="hidden"
          onChange={(e) => subir("carga", e.target.files?.[0])} />
        <button onClick={() => entradaFinal.current?.click()} disabled={ocupado}
          className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-60">
          {procesando === "carga" ? "Cargando..." : "Cargar versión final (PDF)"}
        </button>
        {reemplazando && (
          <button onClick={() => setReemplazando(false)} disabled={ocupado}
            className="rounded-lg border border-slate-300 px-3 py-2 hover:bg-slate-50">
            Cancelar
          </button>
        )}
      </div>
      {reemplazando && (
        <p className="rounded bg-amber-50 p-2 text-amber-800">
          La versión nueva reemplaza a la actual y sus firmas dejan de aplicar: todas las partes deberán firmar otra vez.
        </p>
      )}
    </div>
  );

  return (
    <section className="mx-6 mt-6 rounded-xl bg-white p-5 shadow">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold text-slate-800">Firma electrónica del contrato final</h2>
        {documento && (
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${ESTADOS[documento.estado_firma].clase}`}>
            {ESTADOS[documento.estado_firma].nombre}
          </span>
        )}
      </div>

      {error && <p className="mb-3 rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {aviso && <p className="mb-3 rounded bg-green-50 p-3 text-sm text-green-800">{aviso}</p>}

      {cargando ? (
        <p className="text-sm text-slate-500">Cargando...</p>
      ) : !documento || reemplazando ? (
        formularioCarga
      ) : (
        <div className="space-y-5 text-sm">
          {/* Datos del documento */}
          <div className="grid gap-2 sm:grid-cols-2">
            <p className="text-slate-600">
              Documento: <span className="font-medium text-slate-800">{documento.nombre_archivo}</span>
              <span className="text-slate-500"> · versión {documento.numero_version}</span>
            </p>
            <p className="text-slate-600 tabular-nums">
              Firmas: <span className="font-medium text-slate-800">{documento.numero_firmas} de {documento.numero_firmas_requeridas}</span>
            </p>
            <p className="min-w-0 text-slate-600 sm:col-span-2">
              Huella SHA-256 vigente:{" "}
              <button onClick={() => copiarHash(documento.hash_vigente)} title="Copiar huella completa"
                className="break-all font-mono text-xs text-slate-800 hover:text-blue-700">
                {documento.hash_vigente}
              </button>
              {copiado && <span className="ml-2 text-xs text-green-700">¡Copiada!</span>}
            </p>
          </div>

          {/* Acciones */}
          <div className="flex flex-wrap gap-2">
            {!documento.ya_firme && documento.estado_firma !== "FIRMADO_COMPLETO" && documento.estado_firma !== "INVALIDO" && (
              <button onClick={() => setModalFirma(true)} disabled={ocupado}
                className="rounded-lg bg-blue-600 px-4 py-1.5 font-medium text-white hover:bg-blue-700 disabled:opacity-60">
                Firmar con mi certificado
              </button>
            )}
            <button onClick={descargar} disabled={ocupado}
              className="rounded-lg border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-60">
              {procesando === "descarga" ? "Descargando..." : "Descargar PDF"}
            </button>
            {documento.estado_firma !== "FIRMADO_COMPLETO" && (
              <>
                <input ref={entradaExterna} type="file" accept="application/pdf,.pdf" className="hidden"
                  onChange={(e) => subir("externa", e.target.files?.[0])} />
                <button onClick={() => entradaExterna.current?.click()} disabled={ocupado}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-60">
                  {procesando === "externa" ? "Verificando..." : "Subir PDF firmado con FirmaEC"}
                </button>
              </>
            )}
            <button onClick={verificar} disabled={ocupado || documento.numero_firmas === 0}
              className="rounded-lg border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-60">
              {procesando === "verificar" ? "Verificando..." : "Verificar firmas"}
            </button>
            <button onClick={() => setReemplazando(true)} disabled={ocupado}
              className="ml-auto rounded-lg px-3 py-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-60">
              Cargar otra versión
            </button>
          </div>
          {documento.estado_firma !== "FIRMADO_COMPLETO" && (
            <p className="text-xs text-slate-500">
              Si la otra parte firma con FirmaEC: descarga el PDF, envíaselo, pídele que lo firme sin modificarlo y
              sube aquí el archivo que te devuelva. El sistema comprueba que sea el mismo documento y que la firma sea válida.
            </p>
          )}

          {/* Firmas */}
          <div>
            <h3 className="mb-2 font-medium text-slate-800">Firmas</h3>
            {documento.firmas.length === 0 ? (
              <p className="text-slate-500">Todavía nadie ha firmado.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="p-2">#</th>
                      <th className="p-2">Titular</th>
                      <th className="p-2">Certificado</th>
                      <th className="p-2">Fecha</th>
                      <th className="p-2">Dónde</th>
                      <th className="p-2">Integridad</th>
                      <th className="p-2">Confianza</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documento.firmas.map((f) => (
                      <tr key={f.numero_orden} className="border-t align-top">
                        <td className="p-2 tabular-nums">{f.numero_orden}</td>
                        <td className="p-2">
                          <span className="font-medium text-slate-800">{f.titular}</span>
                          {f.identificacion && <span className="block text-xs text-slate-500">{f.identificacion}</span>}
                          {f.motivo && <span className="block text-xs text-slate-500">«{f.motivo}»</span>}
                        </td>
                        <td className="p-2 text-xs text-slate-600">
                          {f.emisor}
                          <span className="block">Serie {f.numero_serie}</span>
                          <span className="block">Vence {new Date(f.vigencia_hasta).toLocaleDateString("es-EC")}</span>
                        </td>
                        <td className="p-2 whitespace-nowrap tabular-nums">{fecha(f.fecha_firma)}</td>
                        <td className="p-2 text-xs">{f.en_plataforma ? `Plataforma (${f.firmante})` : "Externa (FirmaEC u otra)"}</td>
                        <td className="p-2">
                          {f.es_integra
                            ? <span className="font-medium text-green-700">✓ Íntegra</span>
                            : <span className="font-medium text-red-700">✗ Alterada</span>}
                        </td>
                        <td className="p-2">
                          {f.es_confiable
                            ? <span className="font-medium text-green-700">✓ Entidad reconocida</span>
                            : <span className="text-amber-700" title="El certificado no encadena con ninguna entidad de certificación cargada como de confianza">
                                No verificada
                              </span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {documento.raices_confianza === 0 && documento.firmas.length > 0 && (
              <p className="mt-2 text-xs text-slate-500">
                No hay certificados raíz de confianza cargados en el servidor, por eso no se puede confirmar qué entidad emitió cada certificado.
                La integridad sí está verificada.
              </p>
            )}
          </div>

          {/* Cambios acordados */}
          <div>
            <h3 className="mb-2 font-medium text-slate-800">¿La versión final incluye lo acordado?</h3>
            {documento.cambios === null ? (
              <p className="text-slate-500">El PDF no tiene texto seleccionable (parece escaneado), así que no se pudo comprobar.</p>
            ) : documento.cambios.length === 0 ? (
              <p className="text-slate-500">No marcaste contrapropuestas como aceptadas.</p>
            ) : (
              <ul className="divide-y rounded-lg border">
                {documento.cambios.map((k) => (
                  <li key={k.id_clausula} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                    <button onClick={() => onIrAClausula(k.id_clausula)} className="text-left text-blue-700 hover:underline">
                      Cláusula #{k.numero_clausula}{k.titulo_clausula && `: ${k.titulo_clausula}`}
                      <span className="ml-2 text-xs text-slate-500">({k.estado_nombre.toLowerCase()})</span>
                    </button>
                    <span className={`font-medium tabular-nums ${RESULTADOS[k.resultado].clase}`}>
                      {RESULTADOS[k.resultado].nombre} · {k.porcentaje} %
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {documento.cambios?.some((k) => k.resultado !== "INCLUIDA") && (
              <p className="mt-2 text-xs text-amber-800">
                Revisa las cláusulas marcadas antes de firmar: la otra parte pudo haber cambiado la redacción acordada.
              </p>
            )}
          </div>
        </div>
      )}

      {documento && (
        <ModalFirma abierto={modalFirma} idContrato={idContrato} nombreDocumento={documento.nombre_archivo}
          onFirmado={(d) => { setDocumento(d); setAviso("Documento firmado correctamente."); }}
          onCerrar={() => setModalFirma(false)} />
      )}
    </section>
  );
}