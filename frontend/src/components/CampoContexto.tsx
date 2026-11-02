import { MAX_CONTEXTO, type OpcionCatalogo } from "../types";

interface Props {
  roles: OpcionCatalogo[];
  rol: string;
  onRol: (codigo: string) => void;
  contexto: string;
  onContexto: (texto: string) => void;
}

const EJEMPLO =
  "Ej.: Servicio de asistente administrativa para la urbanización. Horario de 08:00 a 17:00, " +
  "de lunes a viernes; no incluye fines de semana. Cualquier actividad adicional se paga aparte. " +
  "Pago mensual de $600 los primeros 5 días de cada mes.";

/** Papel del usuario en el contrato y lo que dice que acordaron con la otra parte. */
export default function CampoContexto({ roles, rol, onRol, contexto, onContexto }: Props) {
  return (
    <div className="space-y-3">
      <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <legend className="mb-1 font-medium text-slate-700">Mi papel en el contrato</legend>
        {roles.map((r) => (
          <label key={r.codigo} className="flex items-center gap-1.5">
            <input type="radio" name="rol_parte" value={r.codigo} checked={rol === r.codigo}
              onChange={() => onRol(r.codigo)} />
            {r.nombre}
          </label>
        ))}
      </fieldset>
      <div>
        <label htmlFor="contexto_usuario" className="text-sm font-medium text-slate-700">
          Lo que acordaron <span className="font-normal text-slate-500">(opcional, en tus palabras)</span>
        </label>
        <textarea id="contexto_usuario" rows={4} maxLength={MAX_CONTEXTO} value={contexto}
          onChange={(e) => onContexto(e.target.value)} placeholder={EJEMPLO}
          className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" />
        <p className="flex justify-between text-xs text-slate-500">
          <span>El sistema revisará si cada condición está en el contrato.</span>
          <span className="tabular-nums">{contexto.length} / {MAX_CONTEXTO}</span>
        </p>
      </div>
    </div>
  );
}