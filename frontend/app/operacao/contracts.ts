export type User = { id: number; nome: string; papel: "gestor" | "bdr" | "executivo"; gravacao?: boolean };
export type Campaign = { id: number; tag: string; importados_visiveis: number };
export const bantLabels = { orcamento: "Orçamento", autoridade: "Autoridade", necessidade: "Necessidade", prazo: "Prazo" };
export type BantField = keyof typeof bantLabels;
export type Lead = {
  id: number;
  versao?: number;
  razao_social: string;
  nome_fantasia: string | null;
  cnpj: string | null;
  segmento: string | null;
  etapa: string;
  nota_final: number | null;
  solucao_principal: string | null;
  responsavel_id: number | null;
  sla_limite: string | null;
  retorno_em: string | null;
  base_contato: string;
  contato_autorizado: boolean;
  campanhas?: { id: number; tag: string }[];
  bant?: Record<BantField, { preenchido: boolean; confirmado: boolean }>;
  cadencia?: { id?: number; dia: number; canal: string; previsto_para: string; feito_em: string | null }[];
  atividades?: { tipo: string; resultado: string | null; registrada_em: string }[];
};
export type Options = {
  estado: Record<string, string[]>;
  motivos: string[];
  resultados: string[];
  classificacoes: string[];
  solucoes: { id: string; nome: string }[];
  executivos: { id: number; nome: string }[];
  bdrs: { id: number; nome: string }[];
  triagem: string[];
  processaveis: string[];
};
export type Command = { acao: string; [key: string]: unknown };
export type RunCommand = <T>(payload: Command) => Promise<T>;
export const target = (lead: Lead) => ({ id: lead.id, versao: lead.versao });

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api/operacao/" + path, { ...init, cache: "no-store", credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, data.detail || "Falha na consulta.");
  return data as T;
}

export const control = "rounded-lg border border-border bg-background px-3 py-2 text-sm";
export const primary = "nav-active rounded-lg px-3 py-2 text-sm font-semibold disabled:opacity-40";
export const formatDate = (value: string) =>
  new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Sao_Paulo" }).format(new Date(value));
