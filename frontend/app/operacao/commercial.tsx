"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Card } from "@/components/ui/card";
import { api, control, formatDate, primary, type Command, type Options, type User } from "./contracts";

type ErrorHandler = (error: unknown) => void;
type Shared = {
  user: User; options: Options | null; revision: number; pending: boolean;
  submit: (command: Command) => void; onError: ErrorHandler;
};
type LeadRef = { id: number; versao: number };
type BoardItem = LeadRef & { razao_social: string; nome_fantasia: string | null; executivo: string | null; valor_mensal: number | null };
type Board = { colunas: { etapa: string; items: BoardItem[]; total: number; valor: number }[] };
type Detail = {
  movimentos: string[]; posso_passar: boolean;
  oportunidade: { solucoes: string[]; valor_mensal: number | null; previsao_fechamento: string | null; executivo: string | null; resumo_passagem?: string } | null;
  historico: { fase: string; quando: string; texto: string }[];
};
type Appointment = {
  id: number; lead_id: number; versao: number; empresa: string; tipo: string; titulo: string;
  inicio_em: string; status: string; responsavel: string;
};
export const money = (value: number) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);

export function useOperational<T>(path: string | null, revision: number, onError: ErrorHandler) {
  const [data, setData] = useState<{ path: string; revision: number; value: T } | null>(null);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    api<T>(path, { signal: controller.signal }).then((value) => setData({ path, revision, value }))
      .catch((error) => { if (!controller.signal.aborted) onError(error); });
    return () => controller.abort();
  }, [path, revision, onError]);
  return data?.path === path && data?.revision === revision ? data.value : null;
}

function Field({ name, title, type = "text", value, required = true }: {
  name: string; title: string; type?: string; value?: string | number; required?: boolean;
}) {
  return <label className="grid gap-1 text-sm">{title}<input name={name} type={type} defaultValue={value}
    required={required} step={type === "number" ? "0.01" : undefined} min={type === "number" ? 0 : undefined}
    maxLength={type === "text" ? 180 : undefined} className={`min-w-0 ${control}`} /></label>;
}

function AppointmentList({ data, shared }: { data: Appointment[]; shared: Shared }) {
  const [editing, setEditing] = useState<number | null>(null);
  return <ul className="divide-y divide-border">{data.map((item) => {
    const args = { leads: [{ id: item.lead_id, versao: item.versao }], compromisso: item.id };
    return <li key={item.id} className="grid gap-2 py-3 text-sm">
      <strong>{item.titulo}</strong>
      <p className="text-muted">{item.empresa} · {item.tipo} · {formatDate(item.inicio_em)} · {item.responsavel} · {item.status}</p>
      {shared.user.gravacao && item.status === "Pendente" && <div className="flex flex-wrap gap-2">
        <button type="button" className={control} disabled={shared.pending}
          onClick={() => shared.submit({ acao: "agenda-resolver", ...args, status: "Concluído" })}>Concluir</button>
        <button type="button" className={control} disabled={shared.pending}
          onClick={() => setEditing(editing === item.id ? null : item.id)}>Reagendar</button>
        <button type="button" className={control} disabled={shared.pending}
          onClick={() => shared.submit({ acao: "agenda-resolver", ...args, status: "Cancelado" })}>Cancelar</button>
      </div>}
      {editing === item.id && item.status === "Pendente" && <form className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          shared.submit({ acao: "agenda-reagendar", ...args, inicio: new FormData(event.currentTarget).get("inicio") });
          setEditing(null);
        }}>
        <Field name="inicio" type="datetime-local" title="Novo horário de Brasília" />
        <button className={primary} disabled={shared.pending}>Salvar horário</button>
      </form>}
    </li>;
  })}</ul>;
}

export function AgendaPanel({ shared, lead }: { shared: Shared; lead?: LeadRef }) {
  const [status, setStatus] = useState("Pendente");
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({ status, offset: String(offset), limit: "20" });
  if (lead) params.set("lead_id", String(lead.id));
  const agenda = useOperational<{ items: Appointment[] }>("agenda?" + params, shared.revision, shared.onError);
  return <section className="space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-semibold">{lead ? "Compromissos do lead" : "Agenda comercial"}</h2>
      <select className={control} aria-label="Status da agenda" value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}>
        {["Pendente", "Concluído", "Cancelado", "Todos"].map((item) => <option key={item}>{item}</option>)}
      </select>
    </div>
    {agenda ? agenda.items.length ? <AppointmentList data={agenda.items} shared={shared} />
      : <p className="text-sm text-muted">Sem compromissos neste filtro.</p>
      : <p role="status" className="text-sm text-muted">Carregando agenda…</p>}
    {(offset > 0 || agenda?.items.length === 20) && <div className="flex gap-2">
      <button className={control} disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 20))}>Anterior</button>
      <button className={control} disabled={agenda?.items.length !== 20} onClick={() => setOffset(offset + 20)}>Próxima</button>
    </div>}
  </section>;
}

export function ScheduleForm({ lead, shared }: { lead: LeadRef; shared: Shared }) {
  if (!shared.user.gravacao) return null;
  return <form className="grid min-w-0 gap-2" onSubmit={(event) => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    shared.submit({ acao: "agenda-criar", leads: [lead], tipo: fields.get("tipo"), titulo: fields.get("titulo"), inicio: fields.get("inicio") });
  }}>
    <label className="grid gap-1 text-sm">Tipo de compromisso
      <select name="tipo" aria-label="Tipo de compromisso" className={control}>
        {["Tarefa interna", "Retorno", "Reunião planejada", "Reunião confirmada"].map((item) => <option key={item}>{item}</option>)}
      </select>
    </label>
    <Field name="titulo" title="Título do compromisso" />
    <Field name="inicio" title="Horário de Brasília" type="datetime-local" />
    <button className={primary} disabled={shared.pending}>Agendar</button>
  </form>;
}

function DealForm({ lead, detail, shared }: { lead: BoardItem; detail: Detail; shared: Shared }) {
  const [action, setAction] = useState("oportunidade");
  const [stage, setStage] = useState("");
  const options = shared.options;
  if (!options || !shared.user.gravacao) return null;

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const common = { acao: action, leads: [{ id: lead.id, versao: lead.versao }] };
    if (action === "oportunidade") shared.submit({ ...common, solucoes: fields.getAll("solucoes"),
      valor: fields.get("valor") ? Number(fields.get("valor")) : null, previsao: fields.get("previsao") || null });
    if (action === "passagem") shared.submit({ ...common, solucoes: fields.getAll("solucoes"),
      executivo: Number(fields.get("executivo")), inicio: fields.get("inicio") });
    if (action === "crm-status") shared.submit({ ...common, etapa: stage,
      motivo: fields.get("motivo") || null, justificativa: fields.get("justificativa") });
  }

  return <form className="grid gap-3" onSubmit={apply}>
    <label className="grid gap-1 text-sm">Ação comercial
      <select aria-label="Ação comercial" value={action} onChange={(event) => setAction(event.target.value)} className={control}>
        <option value="oportunidade">Editar oportunidade</option>
        {detail.posso_passar && <option value="passagem">Passar ao executivo</option>}
        {detail.movimentos.length > 0 && <option value="crm-status">Mover no Kanban</option>}
      </select>
    </label>
    {action !== "crm-status" && <label className="grid gap-1 text-sm">Soluções
      <select name="solucoes" aria-label="Soluções" multiple required className={control} defaultValue={detail.oportunidade?.solucoes ?? []}>
        {options.solucoes.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
      </select>
    </label>}
    {action === "oportunidade" && <>
      <Field name="valor" title="Valor mensal estimado (R$)" type="number" value={detail.oportunidade?.valor_mensal ?? undefined} required={false} />
      <Field name="previsao" title="Previsão de fechamento" type="date" value={detail.oportunidade?.previsao_fechamento ?? undefined} required={false} />
    </>}
    {action === "passagem" && <>
      <label className="grid gap-1 text-sm">Executivo
        <select name="executivo" aria-label="Executivo" required className={control} defaultValue="">
          <option value="">Selecionar</option>
          {options.executivos.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
        </select>
      </label>
      <Field name="inicio" type="datetime-local" title="Horário da reunião em Brasília" />
    </>}
    {action === "crm-status" && <>
      <label className="grid gap-1 text-sm">Etapa de destino
        <select aria-label="Etapa de destino" required className={control} value={stage} onChange={(event) => setStage(event.target.value)}>
          <option value="">Selecionar</option>
          {detail.movimentos.map((item) => <option key={item}>{item}</option>)}
        </select>
      </label>
      <Field name="justificativa" title="Justificativa comercial" />
      {stage === "Perdido" && <label className="grid gap-1 text-sm">Motivo da perda
        <select name="motivo" aria-label="Motivo da perda" required className={control} defaultValue="">
          <option value="">Selecionar</option>{options.motivos.map((item) => <option key={item}>{item}</option>)}
        </select>
      </label>}
    </>}
    <button disabled={shared.pending} className={primary}>Salvar no CRM</button>
  </form>;
}

export function Crm({ shared, onConsult }: { shared: Shared; onConsult: (id: number) => void }) {
  const [search, setSearch] = useState("");
  const [term, setTerm] = useState("");
  const [more, setMore] = useState({ stage: "", page: 1 });
  const [active, setActive] = useState<BoardItem | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const activeId = active?.id;
  useEffect(() => {
    if (activeId !== undefined && window.matchMedia("(max-width: 1023px)").matches) heading.current?.focus();
  }, [activeId]);
  const [section, setSection] = useState<"oportunidade" | "agenda" | "historico">("oportunidade");
  const params = new URLSearchParams({ termo: term, etapa: more.stage, pagina: String(more.page) });
  const board = useOperational<Board>("crm?" + params, shared.revision, shared.onError);
  const live = board?.colunas.flatMap((column) => column.items).find((item) => item.id === active?.id);
  const lead = live ?? active;
  const detail = useOperational<Detail>(lead ? "crm/" + lead.id : null, shared.revision, shared.onError);
  // Uma mudança pode remover o cartão da primeira página. Busque a versão atual da ficha separadamente.
  const current = useOperational<LeadRef>(lead ? "leads/" + lead.id : null, shared.revision, shared.onError);

  return <>
    <Card className="min-w-0">
      <form className="mb-4 flex flex-wrap items-end gap-2" onSubmit={(event) => {
        event.preventDefault(); setTerm(search.trim()); setMore({stage:"",page:1});
      }}>
        <label className="grid gap-1 text-sm">Empresa ou CNPJ<input className={control} value={search} maxLength={100}
          onChange={(event) => setSearch(event.target.value)} /></label>
        <button className={primary}>Buscar</button>
      </form>
      <div tabIndex={0} role="region" aria-label="Kanban comercial" className="grid auto-cols-[minmax(13rem,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2">
        {board?.colunas.map((column) => <section key={column.etapa} className="min-w-0 rounded-xl border border-border bg-background p-3">
          <h2 className="font-semibold">{column.etapa}</h2>
          <p className="mb-2 text-xs text-muted">{column.total} · {money(column.valor)}/mês</p>
          {column.items.map((item) => <button type="button" key={item.id} aria-pressed={active?.id === item.id}
            onClick={() => { setActive(item); setSection("oportunidade"); }}
            className="mb-2 grid w-full gap-1 rounded-lg border border-border bg-card p-2 text-left text-sm hover:text-primary aria-pressed:border-primary">
            <strong className="break-words">{item.nome_fantasia || item.razao_social}</strong>
            {item.valor_mensal !== null && <span className="text-muted">{money(item.valor_mensal)}/mês</span>}
          </button>)}
          {column.total > column.items.length && <button type="button" className={control}
            onClick={() => setMore({ stage: column.etapa, page: more.stage === column.etapa ? more.page + 1 : 2 })}>Mostrar mais</button>}
        </section>)}
        {!board && <p role="status" className="text-sm text-muted">Carregando Kanban…</p>}
      </div>
    </Card>
    {lead && <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 ref={heading} tabIndex={-1} className="font-semibold">{lead.razao_social}</h2>
        <button className={control} onClick={() => onConsult(lead.id)}>Consultar assistente</button>
      </div>
      <div className="my-3 flex flex-wrap gap-2" role="group" aria-label="Seções da oportunidade">
        {(["oportunidade", "agenda", "historico"] as const).map((item) => <button key={item} aria-pressed={item === section}
          className={item === section ? primary : control} onClick={() => setSection(item)}>
          {{ oportunidade: "Oportunidade", agenda: "Agenda do lead", historico: "Histórico" }[item]}
        </button>)}
      </div>
      {detail && current ? section === "oportunidade" ? <>
        {detail.oportunidade && <p className="mb-3 text-sm text-muted">
          {detail.oportunidade.valor_mensal === null ? "Valor a estimar" : money(detail.oportunidade.valor_mensal) + "/mês"} · {detail.oportunidade.executivo || "Sem executivo"}
        </p>}
        {detail.oportunidade?.resumo_passagem && <details className="mb-4 text-sm">
          <summary className="cursor-pointer font-semibold">Resumo da passagem</summary>
          <p className="mt-2 whitespace-pre-line text-muted">{detail.oportunidade.resumo_passagem}</p>
        </details>}
        <DealForm key={`${lead.id}-${current.versao}`} lead={{ ...lead, versao: current.versao }} detail={detail} shared={shared} />
      </> : section === "agenda" ? <div className="grid gap-5 lg:grid-cols-2">
        <AgendaPanel key={lead.id} shared={shared} lead={{ id: lead.id, versao: current.versao }} />
        <ScheduleForm shared={shared} lead={{ id: lead.id, versao: current.versao }} />
      </div> : <ol className="divide-y divide-border">{detail.historico.map((event, index) => <li key={index} className="py-2 text-sm">
        <strong>{event.fase}</strong> <span className="text-muted">· {formatDate(event.quando)}</span><p>{event.texto}</p>
      </li>)}</ol> : <p role="status">Carregando ficha comercial…</p>}
    </Card>}
  </>;
}

export function LeadPicker({ revision, onError, value, onChange }: {
  revision: number; onError: ErrorHandler; value: LeadRef | null; onChange: (value: LeadRef | null) => void;
}) {
  const [input, setInput] = useState("");
  const [term, setTerm] = useState("");
  const params = new URLSearchParams({ termo: term, limit: "30" });
  const result = useOperational<{ items: (LeadRef & { razao_social: string })[] }>("leads?" + params, revision, onError);
  const chosen = useOperational<LeadRef & { razao_social: string }>(value ? "leads/" + value.id : null, revision, onError);
  return <div className="grid gap-2">
    <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); setTerm(input.trim()); }}>
      <label className="grid gap-1 text-sm">Empresa ou CNPJ<input className={control} value={input} maxLength={100}
        onChange={(event) => setInput(event.target.value)} /></label>
      <button className={control}>Buscar</button>
    </form>
    <label className="grid gap-1 text-sm">Lead
      <select aria-label="Lead" className={`min-w-0 ${control}`} value={value?.id ?? ""} onChange={(event) => {
        const item = result?.items.find((lead) => lead.id === Number(event.target.value));
        onChange(item ? { id:item.id, versao:item.versao } : null);
      }}>
        <option value="">Selecionar</option>
        {chosen && !result?.items.some((item) => item.id === chosen.id) && <option value={chosen.id}>{chosen.razao_social}</option>}
        {result?.items.map((item) => <option key={item.id} value={item.id}>{item.razao_social}</option>)}
      </select>
    </label>
  </div>;
}

export function AgendaWorkspace({ shared }: { shared: Shared }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<LeadRef | null>(null);
  const current = useOperational<LeadRef>(active ? "leads/" + active.id : null, shared.revision, shared.onError);
  return <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
    <Card><AgendaPanel shared={shared} /></Card>
    {shared.user.gravacao && <Card className="self-start">
      <button type="button" className={open ? control : primary} aria-expanded={open} onClick={() => setOpen(!open)}>Novo compromisso</button>
      {open && <div className="mt-3 grid gap-3">
        <LeadPicker revision={shared.revision} onError={shared.onError} value={active} onChange={setActive} />
        {current && <ScheduleForm shared={shared} lead={{ id:current.id, versao:current.versao }} />}
      </div>}
    </Card>}
  </div>;
}
