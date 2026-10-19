import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { useAuth } from "../context/AuthContext";
import { getErrorMessage } from "../api/client";
import type { RegisterData } from "../types";

const input =
  "w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<RegisterData>({
    email: "", full_name: "", password: "", role: "freelancer", company_name: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function update<K extends keyof RegisterData>(key: K, value: RegisterData[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const payload = { ...form, company_name: form.role === "pyme" ? form.company_name : undefined };
      await register(payload);
      navigate("/");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-8 shadow">
        <h1 className="text-2xl font-bold text-slate-800">Crear cuenta</h1>
        {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

        <div className="grid grid-cols-2 gap-2">
          {(["freelancer", "pyme"] as const).map((r) => (
            <button type="button" key={r} onClick={() => update("role", r)}
              className={`rounded-lg border py-2 text-sm font-medium ${
                form.role === r ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-300 text-slate-600"
              }`}>
              {r === "freelancer" ? "Freelancer" : "PYME"}
            </button>
          ))}
        </div>

        <input className={input} placeholder="Nombre completo" required
          value={form.full_name} onChange={(e) => update("full_name", e.target.value)} />
        {form.role === "pyme" && (
          <input className={input} placeholder="Nombre de la empresa" required
            value={form.company_name} onChange={(e) => update("company_name", e.target.value)} />
        )}
        <input className={input} type="email" placeholder="Correo" required
          value={form.email} onChange={(e) => update("email", e.target.value)} />
        <input className={input} type="password" placeholder="Contraseña (mín. 8 caracteres)"
          required minLength={8} maxLength={64}
          value={form.password} onChange={(e) => update("password", e.target.value)} />

        <button disabled={loading}
          className="w-full rounded-lg bg-blue-600 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {loading ? "Creando cuenta..." : "Registrarme"}
        </button>
        <p className="text-center text-sm text-slate-600">
          ¿Ya tienes cuenta? <Link to="/login" className="text-blue-600 hover:underline">Inicia sesión</Link>
        </p>
      </form>
    </div>
  );
}