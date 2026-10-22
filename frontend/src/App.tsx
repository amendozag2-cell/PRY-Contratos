import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import ContratoPage from "./pages/ContratoPage";
import AdminAuditPage from "./pages/AdminAuditPage";
import AdminCorpusPage from "./pages/AdminCorpusPage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/contratos/:id" element={<ContratoPage />} />
          </Route>
          <Route element={<ProtectedRoute roles={["ADMINISTRADOR"]} />}>
            <Route path="/admin/auditoria" element={<AdminAuditPage />} />
            <Route path="/admin/corpus" element={<AdminCorpusPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}