import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { RegistroDatos, Usuario } from "../types";

interface AuthContextValue {
  usuario: Usuario | null;
  cargando: boolean;
  iniciarSesion: (correo: string, clave: string) => Promise<void>;
  registrarse: (datos: RegistroDatos) => Promise<void>;
  cerrarSesion: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(true);

  async function cargarPerfil() {
    const { data } = await api.get<Usuario>("/auth/perfil");
    setUsuario(data);
  }

  useEffect(() => {
    if (!localStorage.getItem("token")) {
      setCargando(false);
      return;
    }
    cargarPerfil()
      .catch(() => localStorage.removeItem("token"))
      .finally(() => setCargando(false));
  }, []);

  async function iniciarSesion(correo: string, clave: string) {
    // FastAPI espera el login como formulario OAuth2 (username / password)
    const form = new URLSearchParams({ username: correo, password: clave });
    const { data } = await api.post<{ access_token: string }>("/auth/login", form);
    localStorage.setItem("token", data.access_token);
    await cargarPerfil();
  }

  async function registrarse(datos: RegistroDatos) {
    await api.post("/auth/registro", datos);
    await iniciarSesion(datos.correo, datos.clave);
  }

  function cerrarSesion() {
    localStorage.removeItem("token");
    setUsuario(null);
  }

  return (
    <AuthContext.Provider value={{ usuario, cargando, iniciarSesion, registrarse, cerrarSesion }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return ctx;
}