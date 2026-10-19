import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { useAuth } from "../context/AuthContext";
import { getErrorMessage } from "../api/client";

const input =
  "w-full rounded-lg border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
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
        <h1 className="text-2xl font-bold text-slate-800">Iniciar sesión</h1>
        {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        <input className={input} type="email" placeholder="Correo" required
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className={input} type="password" placeholder="Contraseña" required
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <button disabled={loading}
          className="w-full rounded-lg bg-blue-600 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50">
          {loading ? "Ingresando..." : "Ingresar"}
        </button>
        <p className="text-center text-sm text-slate-600">
          ¿No tienes cuenta? <Link to="/register" className="text-blue-600 hover:underline">Regístrate</Link>
        </p>
      </form>
    </div>
  );
}