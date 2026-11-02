export const COLOR_NEUTRO = "#64748B";

/** Color con transparencia a partir de un hexadecimal (#RRGGBB). */
export function conAlfa(hex: string, alfa: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`;
}