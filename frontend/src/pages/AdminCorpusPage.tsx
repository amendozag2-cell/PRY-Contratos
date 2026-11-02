import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, getErrorMessage } from "../api/client";
import type {
  DocumentoRag,
  OpcionCatalogo,
  PaginaFragmentos,
  ResultadoBusqueda,
} from "../types";
import ModalConfirmacion from "../components/ModalConfirmacion";

const input =
  "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none";
const TAMANIO_FRAGMENTOS = 10;

export default function AdminCorpusPage() {
  const [tipos, setTipos] = useState<OpcionCatalogo[]>([]);
  const [documentos, setDocumentos] = useState<DocumentoRag[]>([]);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");

  // Formulario de carga
  const [titulo, setTitulo] = useState("");
  const [tipoFuente, setTipoFuente] = useState("");
  const [referencia, setReferencia] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [claveArchivo, setClaveArchivo] = useState(0);
  const [subiendo, setSubiendo] = useState(false);

    // Confirmación para inactivar
  const [porInactivar, setPorInactivar] = useState<DocumentoRag | null>(null);
  const [inactivando, setInactivando] = useState(false);

  // Vista de fragmentos
  const [docSeleccionado, setDocSeleccionado] = useState<DocumentoRag | null>(null);
  const [fragmentos, setFragmentos] = useState<PaginaFragmentos | null>(null);
  const [paginaFrag, setPaginaFrag] = useState(1);

  // Prueba de búsqueda semántica
  const [consulta, setConsulta] = useState(
    "El pago se realizará a los ciento veinte días posteriores a la entrega del informe final."
  );
  const [busqueda, setBusqueda] = useState<ResultadoBusqueda | null>(null);
  const [buscando, setBuscando] = useState(false);

  function cargarDocumentos() {
    api.get<DocumentoRag[]>("/admin/corpus")
      .then((r) => setDocumentos(r.data))
      .catch((e) => setError(getErrorMessage(e)));
  }

  useEffect(() => {
    api.get<OpcionCatalogo[]>("/admin/corpus/tipos-fuente")
      .then((r) => {
        setTipos(r.data);
        if (r.data.length > 0) setTipoFuente(r.data[0].codigo);
      })
      .catch((e) => setError(getErrorMessage(e)));
    cargarDocumentos();
  }, []);

  useEffect(() => {
    if (!docSeleccionado) return;
    api.get<PaginaFragmentos>(`/admin/corpus/${docSeleccionado.id_documento}/fragmentos`, {
      params: { pagina: paginaFrag, tamanio: TAMANIO_FRAGMENTOS },
    })
      .then((r) => setFragmentos(r.data))
      .catch((e) => setError(getErrorMessage(e)));
  }, [docSeleccionado, paginaFrag]);

  async function subirDocumento(e: FormEvent) {
    e.preventDefault();
    if (!archivo) return;
    setError("");
    setAviso("");
    setSubiendo(true);
    const datos = new FormData();
    datos.append("archivo", archivo);
    datos.append("titulo", titulo);
    datos.append("tipo_fuente", tipoFuente);
    if (referencia.trim()) datos.append("referencia", referencia);
    try {
      const { data } = await api.post<DocumentoRag>("/admin/corpus", datos);
      setAviso(`"${data.titulo}" se agregó al corpus con ${data.numero_fragmentos} fragmentos.`);
      setTitulo("");
      setReferencia("");
      setArchivo(null);
      setClaveArchivo((k) => k + 1);
      cargarDocumentos();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubiendo(false);
    }
  }

    function inactivar(doc: DocumentoRag) {
    setPorInactivar(doc);
  }

  async function confirmarInactivar() {
    if (!porInactivar) return;
    const doc = porInactivar;
    setError("");
    setInactivando(true);
    try {
      await api.patch(`/admin/corpus/${doc.id_documento}/inactivar`);
      setAviso(`"${doc.titulo}" se inactivó.`);
      if (docSeleccionado?.id_documento === doc.id_documento) setDocSeleccionado(null);
      cargarDocumentos();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setInactivando(false);
      setPorInactivar(null);
    }
  }
  async function reactivar(doc: DocumentoRag) {
    setError("");
    try {
      await api.patch(`/admin/corpus/${doc.id_documento}/reactivar`);
      setAviso(`"${doc.titulo}" se reactivó. Sus fragmentos vuelven a usarse en el análisis.`);
      cargarDocumentos();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  async function buscar(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBuscando(true);
    try {
      const { data } = await api.post<ResultadoBusqueda>("/admin/corpus/buscar", { consulta });
      setBusqueda(data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBuscando(false);
    }
  }

  const activos = documentos.filter((d) => d.estado === "A");
  const totalFragmentos = activos.reduce((suma, d) => suma + d.numero_fragmentos, 0);
  const paginasFrag = fragmentos ? Math.max(1, Math.ceil(fragmentos.total / TAMANIO_FRAGMENTOS)) : 1;

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="flex flex-wrap items-center justify-between gap-3 bg-white px-6 py-4 shadow-sm">
        <h1 className="text-lg font-bold text-slate-800">Corpus legal (base de conocimiento RAG)</h1>
        <div className="flex gap-2 text-sm">
          <Link to="/admin/auditoria" className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-50">
            Auditoría
          </Link>
          <Link to="/" className="rounded-lg border border-slate-300 px-3 py-1 hover:bg-slate-50">
            ← Volver al panel
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 p-6">
        {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        {aviso && <p className="rounded bg-green-50 p-3 text-sm text-green-700">{aviso}</p>}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Carga de documentos */}
          <form onSubmit={subirDocumento} className="space-y-3 rounded-xl bg-white p-5 shadow">
            <h2 className="font-semibold text-slate-800">Agregar documento</h2>
            <p className="text-sm text-slate-500">
              PDF con texto seleccionable o TXT, máximo 20 MB. Las leyes se dividen por artículo
              automáticamente.
            </p>
            <input id="corpus_titulo" className={input} placeholder="Título (ej. Código del Trabajo)"
              required minLength={3} maxLength={255} value={titulo} onChange={(e) => setTitulo(e.target.value)} />
            <select id="corpus_tipo" className={input} value={tipoFuente} onChange={(e) => setTipoFuente(e.target.value)}>
              {tipos.map((t) => <option key={t.codigo} value={t.codigo}>{t.nombre}</option>)}
            </select>
            <input id="corpus_referencia" className={input} maxLength={255}
              placeholder="Referencia oficial (ej. Registro Oficial y fecha de última reforma)"
              value={referencia} onChange={(e) => setReferencia(e.target.value)} />
            <input key={claveArchivo} id="corpus_archivo" type="file" accept=".pdf,.txt" required
              onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-slate-200" />
            <button disabled={subiendo || !archivo}
              className="w-full rounded-lg bg-blue-600 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50">
              {subiendo ? "Procesando: extrayendo, fragmentando y vectorizando..." : "Agregar al corpus"}
            </button>
            {subiendo && (
              <p className="text-xs text-slate-500">Un código extenso puede tardar alrededor de un minuto.</p>
            )}
          </form>

          {/* Prueba de recuperación */}
          <form onSubmit={buscar} className="space-y-3 rounded-xl bg-white p-5 shadow">
            <h2 className="font-semibold text-slate-800">Probar búsqueda semántica</h2>
            <p className="text-sm text-slate-500">
              Escriba una cláusula o pregunta. El sistema recupera los fragmentos del corpus con significado más parecido.
            </p>
            <textarea id="corpus_consulta" className={`${input} min-h-28`} required minLength={5} maxLength={2000}
              value={consulta} onChange={(e) => setConsulta(e.target.value)} />
            <button disabled={buscando || totalFragmentos === 0}
              className="w-full rounded-lg bg-slate-800 py-2 font-medium text-white hover:bg-slate-700 disabled:opacity-50">
              {buscando ? "Buscando..." : "Buscar normas relacionadas"}
            </button>
            {totalFragmentos === 0 && (
              <p className="text-xs text-slate-500">Agregue al menos un documento para poder buscar.</p>
            )}
          </form>
        </div>

        {busqueda && (
          <section className="space-y-3 rounded-xl bg-white p-5 shadow">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-semibold text-slate-800">Fragmentos recuperados</h2>
              <span className="text-xs text-slate-500 tabular-nums">
                {busqueda.resultados.length} resultados · {busqueda.tiempo_ms} ms · {busqueda.modelo}
              </span>
            </div>
            {busqueda.resultados.map((r, i) => (
              <article key={r.id_fragmento} className="space-y-2 border-t pt-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-mono text-slate-400">#{i + 1}</span>
                  <span className="font-medium text-slate-800">{r.titulo_documento}</span>
                  {r.articulo_referencia && (
                    <span className="rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                      {r.articulo_referencia}
                    </span>
                  )}
                  <span className="ml-auto flex items-center gap-2 text-xs text-slate-500 tabular-nums">
                    <span className="h-1.5 w-24 overflow-hidden rounded bg-slate-100">
                      <span className="block h-full bg-blue-500" style={{ width: `${Math.max(0, r.similitud) * 100}%` }} />
                    </span>
                    similitud {(r.similitud * 100).toFixed(1)} %
                  </span>
                </div>
                <p className="whitespace-pre-line text-sm text-slate-600">{r.contenido}</p>
              </article>
            ))}
          </section>
        )}

        {/* Documentos del corpus */}
        <section className="rounded-xl bg-white shadow">
          <div className="flex flex-wrap items-baseline justify-between gap-2 p-5 pb-3">
            <h2 className="font-semibold text-slate-800">Documentos del corpus</h2>
            <span className="text-sm text-slate-500 tabular-nums">
              {activos.length} activos · {totalFragmentos} fragmentos vectorizados
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="p-3">Título</th>
                  <th className="p-3">Tipo</th>
                  <th className="p-3">Referencia</th>
                  <th className="p-3 text-right">Fragmentos</th>
                  <th className="p-3">Estado</th>
                  <th className="p-3">Fecha</th>
                  <th className="p-3"></th>
                </tr>
              </thead>
              <tbody>
                {documentos.length === 0 && (
                  <tr><td colSpan={7} className="p-8 text-center text-slate-500">
                    El corpus está vacío. Agregue una ley o una guía de buenas prácticas.
                  </td></tr>
                )}
                {documentos.map((d) => (
                  <tr key={d.id_documento} className={`border-t ${d.estado === "I" ? "text-slate-400" : ""}`}>
                    <td className="p-3 font-medium">{d.titulo}</td>
                    <td className="p-3">{d.tipo_fuente_nombre}</td>
                    <td className="p-3">{d.referencia ?? "—"}</td>
                    <td className="p-3 text-right tabular-nums">{d.numero_fragmentos}</td>
                    <td className="p-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        d.estado === "A" ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"}`}>
                        {d.estado === "A" ? "Activo" : "Inactivo"}
                      </span>
                    </td>
                    <td className="p-3 tabular-nums">{new Date(d.fecha_creacion).toLocaleDateString("es-EC")}</td>
                    <td className="whitespace-nowrap p-3 text-right">
                      <button onClick={() => { setDocSeleccionado(d); setPaginaFrag(1); }}
                        className="rounded-lg border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50">
                        Ver fragmentos
                      </button>
                      {d.estado === "A" ? (
                        <button onClick={() => inactivar(d)}
                          className="ml-2 rounded-lg border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50">
                          Inactivar
                        </button>
                      ) : (
                        <button onClick={() => reactivar(d)}
                          className="ml-2 rounded-lg border border-green-200 px-2 py-1 text-xs text-green-700 hover:bg-green-50">
                          Reactivar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {docSeleccionado && fragmentos && (
          <section className="space-y-3 rounded-xl bg-white p-5 shadow">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-slate-800">Fragmentos de «{docSeleccionado.titulo}»</h2>
              <button onClick={() => setDocSeleccionado(null)} className="text-sm text-slate-500 hover:text-slate-800">
                Cerrar
              </button>
            </div>
            {fragmentos.elementos.map((f) => (
              <article key={f.id_fragmento} className="space-y-1 border-t pt-3">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span className="font-mono">#{f.numero_orden}</span>
                  {f.articulo_referencia && (
                    <span className="rounded bg-blue-50 px-2 py-0.5 font-medium text-blue-700">{f.articulo_referencia}</span>
                  )}
                  <span>{f.contenido.length} caracteres</span>
                </div>
                <p className="whitespace-pre-line text-sm text-slate-600">{f.contenido}</p>
              </article>
            ))}
            <div className="flex items-center justify-end gap-2 text-sm text-slate-600">
              <button disabled={paginaFrag <= 1} onClick={() => setPaginaFrag(paginaFrag - 1)}
                className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-40">Anterior</button>
              <span className="tabular-nums">Página {paginaFrag} de {paginasFrag}</span>
              <button disabled={paginaFrag >= paginasFrag} onClick={() => setPaginaFrag(paginaFrag + 1)}
                className="rounded-lg border border-slate-300 px-3 py-1 disabled:opacity-40">Siguiente</button>
            </div>
          </section>
        )}
      </main>

      <ModalConfirmacion
        abierto={porInactivar !== null}
        tono="peligro"
        titulo="Inactivar documento del corpus"
        mensaje={`"${porInactivar?.titulo ?? ""}" dejará de usarse en el análisis de contratos. Podrá reactivarlo cuando quiera.`}
        textoConfirmar="Inactivar"
        procesando={inactivando}
        onConfirmar={confirmarInactivar}
        onCancelar={() => setPorInactivar(null)}
      />
    </div>
  );
}