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

export type CodigoNivel = "ALTO" | "MEDIO" | "BAJO";

export interface NivelRiesgo {
  codigo: CodigoNivel;
  nombre: string;
  color_hex: string;
  peso: number;
}

/** Norma del corpus citada por el modelo para justificar el diagnóstico. */
export interface Fundamento {
  id_fragmento: number;
  titulo_documento: string;
  articulo_referencia: string | null;
  contenido: string;
  similitud: number;
}

export interface ClausulaContrato {
  id_clausula: number;
  numero_orden: number;
  titulo: string | null;
  contenido: string;
  numero_pagina: number;
  coordenadas: Coordenada[];
  nivel_riesgo: NivelRiesgo | null;
  categoria_riesgo: { codigo: string; nombre: string } | null;
  explicacion: string | null;
  fundamentos: Fundamento[];
  contrapropuesta: Contrapropuesta | null;
}


export type CodigoEstadoContrapropuesta = "GENERADA" | "ACEPTADA" | "MODIFICADA" | "RECHAZADA";

/** Redacción alternativa de una cláusula riesgosa y en qué quedó la negociación. */
export interface Contrapropuesta {
  id_contrapropuesta: number;
  estado: { codigo: CodigoEstadoContrapropuesta; nombre: string; color_hex: string };
  texto_propuesto: string;
  texto_acordado: string | null;
  justificacion: string | null;
  fecha_modificacion: string | null;
}

export type CodigoTonoCorreo = "FORMAL" | "CORDIAL";

/** Correo de negociación redactado para la otra parte. */
export interface CorreoNegociacion {
  id_correo: number;
  destinatario: string | null;
  tono: { codigo: CodigoTonoCorreo; nombre: string };
  asunto: string;
  cuerpo: string;
  fecha_creacion: string;
}

export type CodigoRolParte = "PRESTADOR" | "CONTRATANTE";
export type CodigoCobertura = "CUBIERTA" | "PARCIAL" | "CONTRADICHA" | "AUSENTE";

/** Condición que el usuario indicó y si el contrato la recoge. */
export interface Condicion {
  numero_orden: number;
  descripcion: string;
  cobertura: { codigo: CodigoCobertura; nombre: string; color_hex: string };
  explicacion: string | null;
  id_clausula: number | null;
  numero_clausula: number | null;
  titulo_clausula: string | null;
}

export interface ContratoDetalle extends Contrato {
  resumen: string | null;
  tiempo_procesamiento_ms: number | null;
  fecha_analisis: string | null;
  rol_parte: { codigo: CodigoRolParte; nombre: string } | null;
  contexto_usuario: string | null;
  niveles: NivelRiesgo[];
  clausulas: ClausulaContrato[];
  condiciones: Condicion[];
}

/** Máximo de caracteres de "Lo que acordaron" (igual que en el backend). */
export const MAX_CONTEXTO = 4000;

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