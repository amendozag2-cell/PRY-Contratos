export type Rol = "FREELANCER" | "PYME" | "ADMINISTRADOR";

export interface Usuario {
  id_usuario: number;
  correo: string;
  nombres: string;
  apellidos: string;
  rol: Rol;
  nombre_empresa: string | null;
  ruc_empresa: string | null;
  fecha_creacion: string;
}

export interface RegistroDatos {
  correo: string;
  nombres: string;
  apellidos: string;
  clave: string;
  rol: "FREELANCER" | "PYME";
  nombre_empresa: string;
  ruc_empresa: string;
}

export type EstadoAnalisis = "CARGADO" | "PROCESANDO" | "ANALIZADO" | "ERROR";

export interface Contrato {
  id_contrato: number;
  nombre_archivo: string;
  numero_paginas: number | null;
  estado_analisis: EstadoAnalisis;
  puntaje_riesgo_global: string | null;
  fecha_creacion: string;
}

export interface OpcionCatalogo {
  codigo: string;
  nombre: string;
}

export interface EventoAuditoria {
  id_auditoria: number;
  correo_usuario: string | null;
  accion: string;
  accion_nombre: string;
  tabla_afectada: string | null;
  id_registro: number | null;
  resultado: "EXITO" | "FALLO";
  datos_anteriores: Record<string, unknown> | null;
  datos_nuevos: Record<string, unknown> | null;
  observacion: string | null;
  direccion_ip: string | null;
  fecha_evento: string;
}

export interface PaginaAuditoria {
  elementos: EventoAuditoria[];
  total: number;
  pagina: number;
  tamanio: number;
}

export interface ResumenAdministracion {
  usuarios_activos: number;
  contratos: number;
  eventos_hoy: number;
  accesos_fallidos_hoy: number;
}

// ------------------------------------------------ corpus legal (RAG)
export interface DocumentoRag {
  id_documento: number;
  titulo: string;
  tipo_fuente: string;
  tipo_fuente_nombre: string;
  referencia: string | null;
  numero_fragmentos: number;
  estado: "A" | "I";
  fecha_creacion: string;
}

export interface FragmentoRag {
  id_fragmento: number;
  numero_orden: number;
  articulo_referencia: string | null;
  contenido: string;
}

export interface PaginaFragmentos {
  elementos: FragmentoRag[];
  total: number;
  pagina: number;
  tamanio: number;
}

export interface FragmentoEncontrado {
  id_fragmento: number;
  id_documento: number;
  titulo_documento: string;
  articulo_referencia: string | null;
  contenido: string;
  similitud: number;
}

export interface ResultadoBusqueda {
  consulta: string;
  modelo: string;
  tiempo_ms: number;
  resultados: FragmentoEncontrado[];
}