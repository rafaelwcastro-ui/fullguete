"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Card } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress-bar";
import { money, useOperational } from "./commercial";
import { api, control, primary, type Campaign } from "./contracts";

type AnalyticsResult = {
  funil: { etapa: string; leads: number; conversao: number | null }[];
  sla: { sla_pct: number | null; vencidos_sem_contato: number; mediana_h: number | null };
  receita: { prevista: number; pipeline: number; ganha: number };
  bdr: { bdr: string; leads: number; atividades: number; contatos: number }[];
  campanhas: { tag: string; leads: number; ganhos: number; contatos: number }[];
  ia: { tratamentos: number; leads: number; latencia_ms: number | null; nota_media: number | null;
    plano_b: number; avaliacoes: number; concordancia: number | null };
};
const percent = (value: number | null) => value === null ? "—" : new Intl.NumberFormat("pt-BR", {
  style: "percent", maximumFractionDigits: 1,
}).format(value);
const number = (value: number | null) => value === null ? "—" : new Intl.NumberFormat("pt-BR", {
  maximumFractionDigits: 1,
}).format(value);

function IndicatorTable({ title, headers, data }: { title: string; headers: string[]; data: (string | number)[][] }) {
  return <Card className="min-w-0"><h2 className="font-semibold">{title}</h2>
    {data.length ? <div tabIndex={0} role="region" aria-label={title} className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-sm"><thead><tr className="border-b border-border text-muted">
        {headers.map((item) => <th scope="col" key={item} className="p-2">{item}</th>)}
      </tr></thead><tbody className="divide-y divide-border">
        {data.map(([label, ...values], index) => <tr key={index}><th scope="row" className="p-2 font-medium">{label}</th>
          {values.map((value, column) => <td className="p-2 tabular-nums" key={column}>{value}</td>)}
        </tr>)}
      </tbody></table>
    </div> : <p className="mt-3 text-sm text-muted">Sem registros no recorte.</p>}
  </Card>;
}

export function Analytics({ campaigns, revision, onError }: {
  campaigns: Campaign[]; revision: number; onError: (error: unknown) => void;
}) {
  const [days, setDays] = useState("30");
  const [campaign, setCampaign] = useState("");
  const params = new URLSearchParams({ dias: days });
  if (campaign) params.set("campaign_id", campaign);
  const result = useOperational<AnalyticsResult>("analytics?" + params, revision, onError);
  return <>
    <Card className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="font-semibold">Analytics operacional</h2>
      <div className="flex flex-wrap gap-2">
        <select className={control} aria-label="Período de captura" value={days} onChange={(event) => setDays(event.target.value)}>
          <option value="30">Últimos 30 dias</option><option value="90">Últimos 90 dias</option><option value="0">Todo o período</option>
        </select>
        <select className={`max-w-full ${control}`} aria-label="Campanha do Analytics" value={campaign}
          onChange={(event) => setCampaign(event.target.value)}>
          <option value="">Todas as campanhas</option>{campaigns.map((item) => <option key={item.id} value={item.id}>{item.tag}</option>)}
        </select>
      </div>
    </Card>
    {result ? <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ["Conversão em ganho", percent(result.funil[0].leads ? result.funil.at(-1)!.leads / result.funil[0].leads : null)],
          ["SLA de primeiro contato", percent(result.sla.sla_pct)],
          ["Receita mensal prevista", money(result.receita.prevista)],
          ["Receita mensal ganha", money(result.receita.ganha)],
        ].map(([label, value]) => <Card key={label} className="metric-panel">
          <h3 className="text-sm text-muted">{label}</h3><p className="mt-2 break-words text-2xl font-semibold">{value}</p>
        </Card>)}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><h2 className="font-semibold">Conversão por etapa</h2>
          <ul className="mt-3 space-y-3">{result.funil.map((stage) => <li key={stage.etapa}>
            <div className="mb-1 flex justify-between gap-2 text-sm"><span>{stage.etapa}</span>
              <span>{stage.leads}{stage.conversao !== null ? " · " + percent(stage.conversao) : ""}</span></div>
            <ProgressBar value={result.funil[0].leads ? stage.leads / result.funil[0].leads * 100 : 0} label={stage.etapa} />
          </li>)}</ul>
        </Card>
        <Card><h2 className="font-semibold">Desempenho da IA e SLA</h2>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">{[
            ["Tratamentos concluídos", result.ia.tratamentos], ["Leads tratados", result.ia.leads],
            ["Nota média", number(result.ia.nota_media)], ["Latência média (ms)", number(result.ia.latencia_ms)],
            ["Plano B", result.ia.plano_b], ["Concordância humana", percent(result.ia.concordancia)],
            ["Avaliações humanas", result.ia.avaliacoes], ["SLA vencido sem contato", result.sla.vencidos_sem_contato],
            ["Mediana até o contato (h)", number(result.sla.mediana_h)], ["Pipeline mensal", money(result.receita.pipeline)],
          ].map(([label, value]) => <div key={label} className="rounded-lg border border-border p-3">
            <dt className="text-muted">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>)}</dl>
        </Card>
        <IndicatorTable title="Produtividade BDR" headers={["BDR", "Leads trabalhados", "Atividades", "Contatos"]}
          data={result.bdr.map((item) => [item.bdr, item.leads, item.atividades, item.contatos])} />
        <IndicatorTable title="Campanhas" headers={["Campanha", "Leads", "Contatos", "Ganhos"]}
          data={result.campanhas.map((item) => [item.tag, item.leads, item.contatos, item.ganhos])} />
      </div>
    </> : <p role="status">Carregando indicadores…</p>}
  </>;
}

type Answer = {
  texto: string; fontes: string[];
  carteira?: { revisao: number; vencidos: number; propostas: number };
  oportunidades?: { id: number; empresa: string; etapa: string }[];
};

export function Assistant({ active, setActive, revision, onError }: {
  active: number | null; setActive: (id: number | null) => void; revision: number; onError: (error: unknown) => void;
}) {
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const leads = useOperational<{ items: { id: number; razao_social: string }[] }>("leads?limit=100", revision, onError);
  const selected = useOperational<{ id: number; razao_social: string }>(active ? "leads/" + active : null, revision, onError);
  useEffect(() => { setAnswer(null); }, [active, revision]);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;
    setPending(true); setAnswer(null);
    try {
      setAnswer(await api<Answer>("assistente", { method:"POST", headers:{ "Content-Type":"application/json" },
        body: JSON.stringify({ pergunta:question.trim(), lead_id:active }) }));
    } catch (error) { onError(error); }
    finally { setPending(false); }
  }

  return <Card className="max-w-4xl">
    <h2 className="font-semibold">Assistente comercial</h2>
    <form onSubmit={ask} className="mt-4 grid gap-4">
      <label className="grid gap-1 text-sm">Contexto
        <select disabled={pending} aria-label="Contexto" className={control} value={active ?? ""}
          onChange={(event) => setActive(Number(event.target.value) || null)}>
          <option value="">Minha carteira</option>
          {selected && !leads?.items.some((item) => item.id === selected.id) && <option value={selected.id}>{selected.razao_social}</option>}
          {leads?.items.map((item) => <option key={item.id} value={item.id}>{item.razao_social}</option>)}
        </select>
      </label>
      <div className="flex flex-wrap gap-2">
        {(active ? ["Qual é o próximo passo?", "Prepare-me para a reunião", "Mostre o histórico de atividades"]
          : ["Quais oportunidades devo priorizar?", "Onde estão os gargalos da carteira?"]).map((prompt) =>
          <button disabled={pending} key={prompt} type="button" className={control} onClick={() => setQuestion(prompt)}>{prompt}</button>)}
      </div>
      <label className="grid gap-1 text-sm">Pergunta
        <textarea required maxLength={500} value={question} rows={2} className={control} onChange={(event) => setQuestion(event.target.value)} />
      </label>
      <button className={`${primary} w-fit`} disabled={pending}>{pending ? "Consultando…" : "Consultar"}</button>
    </form>
    {answer && <section role="status" className="mt-5 space-y-3 border-t border-border pt-4 text-sm">
      <h3 className="font-semibold">Orientação comercial</h3>
      <p className="whitespace-pre-line break-words">{answer.texto}</p>
      {answer.carteira && <p className="text-muted">{answer.carteira.vencidos} SLA vencidos · {answer.carteira.revisao} em revisão · {answer.carteira.propostas} propostas</p>}
      {!!answer.oportunidades?.length && <ul className="space-y-1">{answer.oportunidades.map((item) => <li key={item.id}>
        <button className="text-primary underline" type="button" onClick={() => setActive(item.id)}>{item.empresa}</button> · {item.etapa}
      </li>)}</ul>}
      {!!answer.fontes.length && <p className="text-muted">Catálogo consultado · {answer.fontes.join(", ")}</p>}
    </section>}
  </Card>;
}
