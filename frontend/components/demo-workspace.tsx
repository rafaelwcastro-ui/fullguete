"use client";

import { useState } from "react";
import { Card } from "@/components/ui/card";
import { queue } from "@/lib/demo";

const sections = {
  prospecting: ["Buscar", "Campanhas", "Qualificação", "Revisão"],
  work: ["Minha fila", "Todos os leads", "Triagem"],
  crm: ["Kanban", "Agenda"],
  assistant: ["Assistente IA"],
  admin: ["Controles"],
} as const;

type Module = keyof typeof sections;
export type Workspace = "overview" | "analytics" | Module;
type Lead = (typeof queue)[number];

const stages = ["Em contato", "Qualificado", "Reunião marcada", "Proposta", "Ganho", "Perdido"];
const normalize = (value: string) => value.toLocaleLowerCase("pt-BR").normalize("NFD").replace(/\p{M}/gu, "");

function includesLead(lead: Lead, section: string) {
  switch (section) {
    case "Minha fila": return lead.etapa !== null;
    case "Triagem": return lead.etapa === null;
    case "Qualificação": return lead.status === "Em análise";
    case "Revisão": return lead.status === "Aguardando avaliação";
    case "Agenda": return lead.agenda !== null;
    default: return true;
  }
}

export function DemoWorkspace({ workspace, initialLead }: { workspace: Module; initialLead: string | null }) {
  const tabs: readonly string[] = sections[workspace];
  const [tab, setTab] = useState(initialLead && workspace === "work" ? "Todos os leads" : tabs[0]);
  const [query, setQuery] = useState("");
  const [campaign, setCampaign] = useState("");
  const [selected, setSelected] = useState(initialLead);
  const [hot, setHot] = useState(false);

  const results = queue.filter((lead) =>
    includesLead(lead, tab) && (!hot || lead.score >= 85) && (!campaign || lead.campanha === campaign) &&
    normalize([lead.empresa, lead.segmento, lead.status].join(" ")).includes(normalize(query.trim())),
  );
  const lead = results.find((item) => item.id === selected);
  const row = (item: Lead) => (
    <button key={item.id} type="button" aria-pressed={selected === item.id} onClick={() => setSelected(item.id)}
      className="flex w-full flex-wrap items-center justify-between gap-2 rounded-lg px-2 py-3 text-left hover:bg-white/5 aria-pressed:bg-white/10">
      <span>
        <span className="block text-sm font-medium">{item.empresa}</span>
        <span className="text-xs text-muted">{item.agenda && tab === "Agenda" ? item.agenda : item.status}</span>
      </span>
      {workspace !== "assistant" && <span className="text-sm font-semibold text-primary" aria-label={`Score ${item.score}`}>{item.score}</span>}
    </button>
  );

  if (workspace === "admin") {
    return <Card><h2 className="font-semibold">Governança e catálogo</h2><p className="mt-2 text-sm text-muted">Os controles operacionais estão disponíveis no portal Streamlit.</p></Card>;
  }

  return (
    <div className="space-y-4">
      {tabs.length > 1 && <div role="group" aria-label="Seções do módulo" className="flex flex-wrap gap-2">
        {tabs.map((name) => <button key={name} type="button" aria-pressed={tab === name}
          onClick={() => { setTab(name); setSelected(null); setQuery(""); setHot(false); setCampaign(""); }}
          className={`rounded-lg px-4 py-2.5 text-sm ${tab === name ? "nav-active font-semibold" : "border border-border bg-card text-muted"}`}>{name}</button>)}
      </div>}
      <Card>
        <h2 className="font-semibold">{workspace === "assistant" ? "Contexto do lead" : tab}</h2>
        {workspace === "assistant" && <p className="mt-2 text-sm text-muted">Selecione uma empresa para consultar a recomendação de exemplo. O chat com o catálogo está disponível no portal Streamlit.</p>}
        {tab === "Campanhas" && <div className="mt-4 text-sm"><label htmlFor="demo-campaign">Campanha</label>
          <select id="demo-campaign" value={campaign} onChange={(event) => { setCampaign(event.target.value); setSelected(null); }}
            className="ml-3 rounded-lg border border-border bg-background px-3 py-2">
            <option value="">Todas</option>
            {[...new Set(queue.map((item) => item.campanha))].map((name) => <option key={name}>{name}</option>)}
          </select>
        </div>}
        {tab !== "Kanban" && <div className="mt-4 flex flex-wrap items-end gap-4">
          <label className="min-w-0 flex-1 text-sm">Buscar empresa de exemplo
            <input value={query} onChange={(event) => setQuery(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-border bg-background px-3 py-2"
              placeholder="Empresa, segmento ou situação" />
          </label>
          {workspace === "work" && <label className="flex min-h-10 items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={hot} onChange={(event) => setHot(event.target.checked)} className="accent-primary" /> Score ≥ 85
          </label>}
        </div>}
        {tab === "Kanban" ? <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {stages.map((stage) => <section key={stage} className="min-h-24 rounded-xl border border-border bg-background p-3">
            <h3 className="mb-2 text-sm font-medium">{stage}</h3>
            {results.filter((item) => item.etapa === stage).map(row)}
          </section>)}
        </div> : <div className="mt-3 divide-y divide-border">
          {results.map(row)}
          {!results.length && <p role="status" className="py-3 text-sm text-muted">Nenhum exemplo encontrado.</p>}
        </div>}
        {lead && <section aria-label={`Ficha de ${lead.empresa}`} className="mt-4 rounded-xl border border-border bg-background p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-semibold">{lead.empresa}</h3>
            <button type="button" onClick={() => setSelected(null)} className="text-sm text-muted underline">Fechar ficha</button>
          </div>
          <p className="mt-2 text-sm text-muted">{lead.segmento} · {lead.campanha} · {lead.status}</p>
          {lead.etapa === null && <p className="mt-2 text-sm text-[#f5ce91]">Contato bloqueado até validação da base legal.</p>}
          <p className="mt-2 text-sm">Próxima ação sugerida: {lead.acao}</p>
        </section>}
      </Card>
    </div>
  );
}
