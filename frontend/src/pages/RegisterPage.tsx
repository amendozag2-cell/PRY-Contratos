import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { useAuth } from "../context/AuthContext";
import { getErrorMessage } from "../api/client";
import type { RegistroDatos } from "../types";

const input =
  "w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none";

export default function RegisterPage() {
  const { registrarse } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<RegistroDatos>({
    correo: "", nombres: "", apellidos: "", clave: "",
    rol: "FREELANCER", nombre_empresa: "", ruc_empresa: "",
  });
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  function actualizar<K extends keyof RegistroDatos>(campo: K, valor: RegistroDatos[K]) {
    setForm((f) => ({ ...f, [campo]: valor }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setEnviando(true);
    try {
      await registrarse(form);
      navigate("/");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setEnviando(false);
    }
  }

  const esPyme = form.rol === "PYME";

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-8 shadow">
        <h1 className="text-2xl font-bold text-slate-800">Crear cuenta</h1>
        {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

        <div className="grid grid-cols-2 gap-2">
          {(["FREELANCER", "PYME"] as const).map((r) => (
            <button type="button" key={r} onClick={() => actualizar("rol", r)}
              className={`rounded-lg border py-2 text-sm font-medium ${
                form.rol === r ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-300 text-slate-600"
              }`}>
              {r === "FREELANCER" ? "Freelancer" : "PYME"}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <input id="nombres" className={input} placeholder="Nombres" required minLength={2} maxLength={80}
            value={form.nombres} onChange={(e) => actualizar("nombres", e.target.value)} />
          <input id="apellidos" className={input} placeholder="Apellidos" required minLength={2} maxLength={80}
            value={form.apellidos} onChange={(e) => actualizar("apellidos", e.target.value)} />
        </div>

        {esPyme && (
          <>
            <input id="nombre_empresa" className={input} placeholder="Nombre de la empresa" required maxLength={150}
              value={form.nombre_empresa} onChange={(e) => actualizar("nombre_empresa", e.target.value)} />
            <input id="ruc_empresa" className={input} placeholder="RUC (13 dígitos, opcional)"
              inputMode="numeric" pattern="\d{13}" title="El RUC debe tener 13 dígitos" maxLength={13}
              value={form.ruc_empresa} onChange={(e) => actualizar("ruc_empresa", e.target.value)} />
          </>
        )}

        <input id="correo" className={input} type="email" placeholder="Correo" required
          value={form.correo} onChange={(e) => actualizar("correo", e.target.value)} />
        <input id="clave" className={input} type="password" placeholder="Contraseña (mín. 8 caracteres)"
          required minLength={8} maxLength={64}
          value={form.clave} onChange={(e) => actualizar("clave", e.target.value)} />

        <button disabled={enviando}
          className="w-full rounded-lg bg-blue-600 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {enviando ? "Creando cuenta..." : "Registrarme"}
        </button>
        <p className="text-center text-sm text-slate-600">
          ¿Ya tienes cuenta? <Link to="/login" className="text-blue-600 hover:underline">Inicia sesión</Link>
        </p>
      </form>
    </div>
  );
}