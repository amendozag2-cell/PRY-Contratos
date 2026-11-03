import { useEffect, useRef } from "react";

interface Props {
  abierto: boolean;
  titulo: string;
  mensaje: string;
  textoConfirmar?: string;
  textoCancelar?: string;
  /** "peligro" pinta el botón de confirmar en rojo (acciones que quitan o inactivan algo). */
  tono?: "peligro" | "normal";
  procesando?: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
}

/** Ventana de confirmación con el estilo del sistema, en lugar del aviso del navegador. */
export default function ModalConfirmacion({
  abierto,
  titulo,
  mensaje,
  textoConfirmar = "Confirmar",
  textoCancelar = "Cancelar",
  tono = "normal",
  procesando = false,
  onConfirmar,
  onCancelar,
}: Props) {
  const botonCancelar = useRef<HTMLButtonElement | null>(null);
  const cancelar = useRef(onCancelar);
  useEffect(() => {
    cancelar.current = onCancelar;
  });

  // Al abrir, el foco va a "Cancelar", que es la opción segura
  useEffect(() => {
    if (abierto) botonCancelar.current?.focus();
  }, [abierto]);

  // Escape cierra el modal (salvo mientras se procesa)
  useEffect(() => {
    if (!abierto) return;
    function alPresionar(e: KeyboardEvent) {
      if (e.key === "Escape" && !procesando) cancelar.current();
    }
    window.addEventListener("keydown", alPresionar);
    return () => window.removeEventListener("keydown", alPresionar);
  }, [abierto, procesando]);

  if (!abierto) return null;

  const peligro = tono === "peligro";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !procesando) onCancelar(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="modal-titulo" aria-describedby="modal-mensaje"
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start gap-4">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${peligro ? "bg-red-100 text-red-600" : "bg-blue-100 text-blue-600"}`}
            aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
              {peligro ? (
                <>
                  <path d="M12 9v4" strokeLinecap="round" />
                  <path d="M12 17h.01" strokeLinecap="round" />
                  <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" strokeLinejoin="round" />
                </>
              ) : (
                <>
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 8h.01M11 12h1v4h1" strokeLinecap="round" strokeLinejoin="round" />
                </>
              )}
            </svg>
          </div>
          <div className="min-w-0">
            <h2 id="modal-titulo" className="text-lg font-semibold text-slate-800">{titulo}</h2>
            <p id="modal-mensaje" className="mt-1 text-sm text-slate-600">{mensaje}</p>
          </div>
        </div>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button ref={botonCancelar} onClick={onCancelar} disabled={procesando}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60">
            {textoCancelar}
          </button>
          <button onClick={onConfirmar} disabled={procesando}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-60 ${peligro ? "bg-red-600 hover:bg-red-700" : "bg-blue-600 hover:bg-blue-700"}`}>
            {procesando ? "Procesando..." : textoConfirmar}
          </button>
        </div>
      </div>
    </div>
  );
}