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
  tipo_contrato: string | null;
  numero_paginas: number | null;
  numero_clausulas: number;
  es_escaneado: boolean;
  estado_analisis: EstadoAnalisis;
  puntaje_riesgo_global: string | null;
  fecha_creacion: string;
}

/** Rectángulo de un párrafo, con valores entre 0 y 1 respecto a la página. */
export interface Coordenada {
  pagina: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface ClausulaContrato {
  id_clausula: number;
  numero_orden: number;
  titulo: string | null;
  contenido: string;
  numero_pagina: number;
  coordenadas: Coordenada[];
}

export interface ContratoDetalle extends Contrato {
  clausulas: ClausulaContrato[];
}

export interface CargaContratoRespuesta {
  contrato: Contrato;
  paginas_ocr: number[];
  tiempo_ms: number;
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