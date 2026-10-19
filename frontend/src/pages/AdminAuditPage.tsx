import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, getErrorMessage } from "../api/client";
import type { OpcionCatalogo, PaginaAuditoria, ResumenAdministracion } from "../types";

const TAMANIO = 20;

function describirDetalle(datos: Record<string, unknown> | null, observacion: string | null) {
  const partes: string[] = [];
  if (observacion) partes.push(observacion);
  if (datos) {
    for (const [clave, valor] of Object.entries(datos)) {
      if (valor !== null && valor !== "") partes.push(`${clave}: ${String(valor)}`);
    }
  }
  return partes.length ? partes.join(" · ") : "—";
}

export default function AdminAuditPage() {
  const [resumen, setResumen] = useState<ResumenAdministracion | null>(null);
  const [acciones, setAcciones] = useState<OpcionCatalogo[]>([]);
  const [datos, setDatos] = useState<PaginaAuditoria | null>(null);
  const [accion, setAccion] = useState("");
  const [resultado, setResultado] = useState("");
  const [correoEscrito, setCorreoEscrito] = useState("");
  const [correo, setCorreo] = useState("");
  const [pagina, setPagina] = useState(1);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<ResumenAdministracion>("/admin/resumen")
      .then((r) => setResumen(r.data))
      .catch((e) => setError(getErrorMessage(e)));
    // Las opciones del filtro vienen del catálogo ACCION_AUDITORIA
    api.get<OpcionCatalogo[]>("/admin/acciones")
      .then((r) => setAcciones(r.data))
      .catch((e) => setError(getErrorMessage(e)));
  }, []);

  // Espera a que el usuario deje de escribir antes de buscar
  useEffect(() => {
    const t = setTimeout(() => {
      setCorreo(correoEscrito.trim());
      setPagina(1);
    }, 400);
    return () => clearTimeout(t);
  }, [correoEscrito]);

  useEffect(() => {
    const params: Record<string, string | number> = { pagina, tamanio: TAMANIO };
    if (accion) params.accion = accion;
    if (resultado) params.resultado = resultado;
    if (correo) params.correo = correo;
    api.get<PaginaAuditoria>("/admin/auditoria", { params })
      .then((r) => setDatos(r.data))
      .catch((e) => setError(getErrorMessage(e)));
  }, [accion, resultado, correo, pagina]);

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.total / TAMANIO)) : 1;
  const tarjetas = resumen
    ? [
        { etiqueta: "Usuarios activos", valor: resumen.usuarios_activos, alerta: false },
        { etiqueta: "Contratos cargados", valor: resumen.contratos, alerta: false },
        { etiqueta: "Eventos hoy", valor: resumen.eventos_hoy, alerta: false },
        { etiqueta: "Accesos fallidos hoy", valor: resumen.accesos_fallidos_hoy, alerta: resumen.accesos_fallidos_hoy > 0 },
      ]
    : [];

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="flex flex-wrap items-center justify-between gap-3 bg-white px-6 py-4 shadow-sm">
        <h1 className="text-lg font-bold text-slate-800">Auditoría del sistema</h1>
        <Link to="/" className="rounded-lg border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50">
          ← Volver al panel
        </Link>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 p-6">
        {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

        {tarjetas.length > 0 && (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {tarjetas.map((t) => (
              <div key={t.etiqueta} className="rounded-xl bg-white p-4 shadow">
                <p className="text-sm text-slate-500">{t.etiqueta}</p>
                <p className={`text-2xl font-bold tabular-nums ${t.alerta ? "text-red-600" : "text-slate-800"}`}>
                  {t.valor}
                </p>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-3 rounded-xl bg-white p-4 shadow">
          <select id="filtro_accion" value={accion} onChange={(e) => { setAccion(e.target.value); setPagina(1); }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="">Todas las acciones</option>
            {acciones.map((a) => <option key={a.codigo} value={a.codigo}>{a.nombre}</option>)}
          </select>
          <select id="filtro_resultado" value={resultado} onChange={(e) => { setResultado(e.target.value); setPagina(1); }}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="">Todos los resultados</option>
            <option value="EXITO">Éxito</option>
            <option value="FALLO">Fallo</option>
          </select>
          <input id="filtro_correo" value={correoEscrito} onChange={(e) => setCorreoEscrito(e.target.value)}
            placeholder="Buscar por correo"
            className="min-w-56 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
        </div>

        <div className="overflow-x-auto rounded-xl bg-white shadow">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="p-3">Fecha y hora</th>
                <th className="p-3">Usuario</th>
                <th className="p-3">Acción</th>
                <th className="p-3">Resultado</th>
                <th className="p-3">Tabla / registro</th>
                <th className="p-3">IP</th>
                <th className="p-3">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {datos?.elementos.length === 0 && (
                <tr><td colSpan={7} className="p-8 text-center text-slate-500">No hay eventos con estos filtros.</td></tr>
              )}
              {datos?.elementos.map((ev) => (
                <tr key={ev.id_auditoria} className="border-t align-top">
                  <td className="whitespace-nowrap p-3 tabular-nums">{new Date(ev.fecha_evento).toLocaleString("es-EC")}</td>
                  <td className="p-3">{ev.correo_usuario ?? "—"}</td>
                  <td className="p-3">{ev.accion_nombre}</td>
                  <td className="p-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      ev.resultado === "EXITO" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {ev.resultado === "EXITO" ? "Éxito" : "Fallo"}
                    </span>
                  </td>
                  <td className="p-3 font-mono text-xs">
                    {ev.tabla_afectada ? `${ev.tabla_afectada} #${ev.id_registro ?? ""}` : "—"}
                  </td>
                  <td className="p-3 font-mono text-xs">{ev.direccion_ip ?? "—"}</td>
                  <td className="p-3 text-slate-600">{describirDetalle(ev.datos_nuevos, ev.observacion)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
          <span>{datos?.total ?? 0} eventos</span>
          <div className="flex items-center gap-2">
            <button disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1 disabled:opacity-40">Anterior</button>
            <span>Página {pagina} de {totalPaginas}</span>
            <button disabled={pagina >= totalPaginas} onClick={() => setPagina(pagina + 1)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1 disabled:opacity-40">Siguiente</button>
          </div>
        </div>
      </main>
    </div>
  );
}