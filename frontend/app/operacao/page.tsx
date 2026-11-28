"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Card } from "@/components/ui/card";
import { BatchActions, LeadActions } from "./actions";
import { CompanySearch } from "./company-search";
import { api, ApiError, bantLabels, control, formatDate, primary, type Campaign, type Command, type Lead, type Options, type User } from "./contracts";

type View = "all" | "queue" | "triage" | "review" | "captured";
type Module = "prospecting" | "work";
type List = { items: Lead[]; total: number; indicadores?: { revisao: number; fila: number; sla_vencido: number } };
const pageSize = 30;

export default function Operacao() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [module, setModule] = useState<Module>("prospecting");
  const [view, setView] = useState<View>("all");
  const [campaign, setCampaign] = useState("");
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<List | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [active, setActive] = useState<number | null>(null);
  const [detail, setDetail] = useState<Lead | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState(false);
  const inFlight = useRef(false);
  const retry = useRef<{ body: string; key: string } | null>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);

  const reset = useCallback(() => {
    retry.current = null;
    setUser(null); setList(null); setDetail(null); setActive(null); setCampaigns([]);
    setSelected([]); setCampaign(""); setOffset(0); setOptions(null); setMessage("");
  }, []);
  const handleError = useCallback((failure: unknown) => {
    if (failure instanceof ApiError && failure.status === 401) reset();
    setError(failure instanceof Error ? failure.message : "A operação não pôde ser concluída.");
  }, [reset]);

  useEffect(() => {
    const controller = new AbortController();
    api<User>("me", { signal: controller.signal }).then(setUser)
      .catch((failure) => {
        if (!controller.signal.aborted && !(failure instanceof ApiError && failure.status === 401)) handleError(failure);
      }).finally(() => { if (!controller.signal.aborted) setChecking(false); });
    return () => controller.abort();
  }, [handleError]);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    api<{ items: Campaign[] }>("campaigns?limit=100", { signal: controller.signal })
      .then(({ items }) => setCampaigns(items))
      .catch((failure) => { if (!controller.signal.aborted) handleError(failure); });
    return () => controller.abort();
  }, [user, revision, handleError]);

  useEffect(() => {
    if (!user?.gravacao) return;
    const controller = new AbortController();
    api<Options>("operation-options", { signal: controller.signal }).then(setOptions)
      .catch((failure) => { if (!controller.signal.aborted) handleError(failure); });
    return () => controller.abort();
  }, [user, handleError]);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    setLoading(true);
    const params = new URLSearchParams({ view, limit: String(pageSize), offset: String(offset) });
    if (campaign) params.set("campaign_id", campaign);
    api<List>("leads?" + params, { signal: controller.signal }).then((result) => {
      if (offset && offset >= result.total) setOffset(Math.floor(Math.max(0, result.total - 1) / pageSize) * pageSize);
      setList(result);
    }).catch((failure) => { if (!controller.signal.aborted) { setList(null); handleError(failure); } })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [user, view, campaign, offset, revision, handleError]);

  useEffect(() => {
    if (!user || active === null) return;
    const controller = new AbortController();
    setDetail(null);
    api<Lead>("leads/" + active, { signal: controller.signal }).then(setDetail).catch((failure) => {
      if (controller.signal.aborted) return;
      if (failure instanceof ApiError && failure.status === 404) setActive(null);
      else handleError(failure);
    });
    return () => controller.abort();
  }, [user, active, revision, handleError]);

  async function run<T>(payload: Command): Promise<T> {
    if (inFlight.current) throw new Error("Aguarde a operação em andamento.");
    const body = JSON.stringify(payload);
    if (retry.current?.body !== body) retry.current = { body, key: crypto.randomUUID() };
    inFlight.current = true;
    setPending(true); setError(""); setMessage("");
    try {
      const result = await api<T>("commands", {
        method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": retry.current.key }, body,
      });
      retry.current = null;
      if (payload.acao !== "buscar") {
        setSelected([]);
        setRevision((current) => current + 1);
        if (payload.acao !== "importar") setMessage("Operação registrada. Ficha e indicadores atualizados.");
      }
      return result;
    } catch (failure) {
      if (failure instanceof ApiError && failure.status < 500) retry.current = null;
      if (failure instanceof ApiError && failure.status === 409) {
        setSelected([]);
        setRevision((current) => current + 1);
      }
      throw failure;
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      await api("session", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: fields.get("login"), senha: fields.get("senha") }),
      });
      setUser(await api<User>("me")); setView("all"); setModule("prospecting");
    } catch (failure) { handleError(failure); }
    finally { setBusy(false); }
  }
  async function signOut() {
    setBusy(true);
    try { await api("session", { method: "DELETE" }); setError(""); }
    catch (failure) { handleError(failure); }
    finally { reset(); setBusy(false); }
  }
  function filter(next: View, nextCampaign = campaign) {
    setView(next); setCampaign(nextCampaign); setOffset(0); setSelected([]); setActive(null); setDetail(null);
  }
  function openLead(id: number) {
    setActive(id);
    if (window.matchMedia("(max-width: 1023px)").matches) detailHeading.current?.focus();
  }
  function toggle(id: number, checked: boolean) {
    setSelected((previous) => checked ? [...previous, id] : previous.filter((item) => item !== id));
  }

  const manager = user?.papel === "gestor";
  const rows = list?.items ?? [];
  const selectedRows = rows.filter((lead) => selected.includes(lead.id));
  const filters: [View, string][] = module === "prospecting"
    ? [["all", "Empresas"], ...(manager && user?.gravacao ? [["captured", "Capturados"] as [View, string]] : []), ["review", "Revisão"]]
    : [...(user?.papel !== "executivo" ? [["queue", "Minha fila"] as [View, string]] : []),
      ["all", "Todos os leads"], ...(manager ? [["triage", "Triagem"] as [View, string]] : [])];
  const submit = (command: Command) => { void run(command).catch(handleError); };

  return <main className="mx-auto min-h-screen max-w-7xl space-y-4 p-4 sm:p-8">
    <header className="flex flex-wrap items-center justify-between gap-3">
      <Image src="/logo.png" alt="Fullguete" width={164} height={43} unoptimized />
      <Link href="/" className="text-sm text-muted underline">Voltar à prévia</Link>
    </header>
    <section className="metric-panel flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border p-5">
      <div><p className="text-xs font-semibold text-primary">Homologação local · {user?.gravacao ? "base fictícia" : "somente leitura"}</p>
        <h1 className="mt-1 text-2xl font-semibold">Prospecção e Central BDR</h1></div>
      {user && <div className="flex items-center gap-4 text-sm">
        <span>{user.nome} <span className="text-muted">· {user.papel}</span></span>
        <button disabled={busy || pending} type="button" onClick={() => void signOut()} className={control}>Sair</button>
      </div>}
    </section>
    {error && <p role="alert" className="rounded-lg border border-border bg-card p-3 text-sm text-[#f5ce91]">{error}</p>}
    {message && <p role="status" className="text-sm text-primary">{message}</p>}
    {checking ? <p role="status" className="text-muted">Verificando sessão…</p> : !user ? <Card className="mx-auto max-w-md">
      <h2 className="font-semibold">Acesso à operação</h2>
      <form onSubmit={signIn} className="mt-4 space-y-4">
        <label className="block text-sm">Usuário<input name="login" required autoComplete="username" className={`mt-1 block w-full ${control}`} /></label>
        <label className="block text-sm">Senha<input name="senha" required autoComplete="current-password" type="password" className={`mt-1 block w-full ${control}`} /></label>
        <button disabled={busy} className={`${primary} w-full`}>Entrar</button>
      </form>
    </Card> : <>
      <nav className="flex flex-wrap gap-2" aria-label="Módulo">
        {(["prospecting", "work"] as const).map((item) => <button key={item} type="button" aria-pressed={module === item}
          onClick={() => { setModule(item); filter(item === "work" && user.papel !== "executivo" ? "queue" : "all", ""); }}
          className={module === item ? primary : control}>{item === "work" ? "Central BDR" : "Prospecção"}</button>)}
      </nav>
      {module === "prospecting" && manager && <CompanySearch writable={!!user.gravacao} pending={pending} run={run} onError={handleError} />}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <Card className="min-w-0">
          <h2 className="font-semibold">Leads autorizados</h2>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {filters.map(([id, label]) => <button key={id} type="button" onClick={() => filter(id)}
              aria-pressed={id === view} className={id === view ? primary : control}>{label}</button>)}
            <select aria-label="Campanha" value={campaign} onChange={(event) => filter(view, event.target.value)} className={`max-w-full ${control}`}>
              <option value="">Todas as campanhas</option>
              {campaigns.map((item) => <option key={item.id} value={item.id}>{item.tag} ({item.importados_visiveis})</option>)}
            </select>
          </div>
          {loading ? <p role="status" className="mt-3 text-sm text-muted">Carregando…</p> : list && <>
            <p className="mt-3 text-xs text-muted">{list.total} registro(s){list.indicadores &&
              ` · ${list.indicadores.revisao} em revisão · ${list.indicadores.fila} na fila · ${list.indicadores.sla_vencido} SLA vencidos`}</p>
            {user.gravacao && options && <BatchActions key={selectedRows.map((item) => item.id).join(",")} leads={selectedRows}
              options={options} manager={manager} pending={pending} submit={submit} />}
            {rows.length ? <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label="Tabela de leads">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border text-xs text-muted"><tr>
                  {user.gravacao && <th scope="col" className="p-2"><input type="checkbox" aria-label="Selecionar todos os leads da página"
                    checked={selectedRows.length === rows.length} onChange={(event) => setSelected(event.target.checked ? rows.map((item) => item.id) : [])} /></th>}
                  <th scope="col" className="p-2">Empresa</th><th scope="col" className="p-2">Etapa</th><th scope="col" className="p-2">Score</th>
                </tr></thead>
                <tbody className="divide-y divide-border">{rows.map((item) => {
                  const name = item.nome_fantasia || item.razao_social;
                  return <tr key={item.id} className={active === item.id ? "bg-white/10" : undefined}>
                    {user.gravacao && <td className="p-2"><input type="checkbox" aria-label={`Selecionar lead ${name}`}
                      checked={selected.includes(item.id)} onChange={(event) => toggle(item.id, event.target.checked)} /></td>}
                    <th scope="row" className="p-2 font-medium"><button type="button" onClick={() => openLead(item.id)} aria-pressed={active === item.id}
                      className="break-words text-left underline decoration-border underline-offset-4 hover:text-primary">{name}</button></th>
                    <td className="p-2 text-xs text-muted">{item.etapa}</td><td className="p-2 text-primary">{item.nota_final ?? "—"}</td>
                  </tr>;
                })}</tbody>
              </table>
            </div> : <p className="py-4 text-sm text-muted">Nenhum registro neste escopo.</p>}
            {list.total > pageSize && <div className="mt-4 flex gap-3">
              <button type="button" disabled={!offset} onClick={() => { setSelected([]); setOffset(offset - pageSize); }} className={`${control} disabled:opacity-40`}>Anterior</button>
              <button type="button" disabled={offset + pageSize >= list.total} onClick={() => { setSelected([]); setOffset(offset + pageSize); }} className={`${control} disabled:opacity-40`}>Próxima</button>
            </div>}
          </>}
        </Card>
        <Card className="min-w-0 self-start lg:sticky lg:top-4 lg:max-h-[calc(100dvh-2rem)] lg:overflow-y-auto">
          <h2 className="font-semibold" ref={detailHeading} tabIndex={-1}>Ficha do lead</h2>
          {detail ? <>
            <div className="mt-3 space-y-2 break-words text-sm">
              <h3 className="font-semibold">{detail.razao_social}</h3>
              <p className="text-muted">{detail.cnpj || "CNPJ não informado"} · {detail.segmento || "Segmento não informado"}</p>
              <p>{detail.etapa} · Score {detail.nota_final ?? "—"}</p>
              {detail.solucao_principal && <p>Solução: {detail.solucao_principal}</p>}
              {!!detail.campanhas?.length && <p>Campanhas: {detail.campanhas.map((item) => item.tag).join(", ")}</p>}
              {manager && options && <p>Responsável: {options.bdrs.find((bdr) => bdr.id === detail.responsavel_id)?.nome
                ?? (detail.responsavel_id ? `#${detail.responsavel_id}` : "Sem atribuição")}</p>}
              {detail.sla_limite && <p>SLA: {formatDate(detail.sla_limite)}</p>}
              {detail.retorno_em && <p>Retorno: {formatDate(detail.retorno_em)}</p>}
              <p className="text-primary">{detail.contato_autorizado ? "Contato autorizado" : "Contato bloqueado pela base legal ou etapa"}</p>
              {detail.bant && <section className="border-t border-border pt-3"><h3 className="font-semibold">BANT progressivo</h3>
                <dl className="mt-2 space-y-1">{Object.entries(bantLabels).map(([field, label]) => {
                  const status = detail.bant?.[field as keyof typeof bantLabels];
                  return <div key={field} className="flex justify-between gap-2"><dt>{label}</dt>
                    <dd className="text-muted">{status?.confirmado ? "Confirmado" : status?.preenchido ? "Preenchido" : "Pendente"}</dd></div>;
                })}</dl></section>}
            </div>
            {user.gravacao && options && <LeadActions key={`${detail.id}-${detail.versao}`} lead={detail} options={options}
              manager={manager} pending={pending} submit={submit} />}
            {!!detail.atividades?.length && <section className="mt-4 border-t border-border pt-4">
              <h3 className="font-semibold">Atividades recentes</h3>
              <ul className="mt-2 space-y-2 text-sm text-muted">{detail.atividades.map((item, index) => <li key={index}>
                {item.tipo} {item.resultado && `· ${item.resultado}`} · {formatDate(item.registrada_em)}</li>)}</ul>
            </section>}
            {!user.gravacao && !!detail.cadencia?.length && <section className="mt-4 border-t border-border pt-4">
              <h3 className="font-semibold">Cadência</h3>
              <ul className="mt-2 text-sm text-muted">{detail.cadencia.map((item, index) => <li key={index}>
                {item.canal} · {item.feito_em ? "Concluído" : "Pendente"}</li>)}</ul>
            </section>}
          </> : <p className="mt-3 text-sm text-muted">{active === null ? "Selecione um lead autorizado." : "Carregando ficha…"}</p>}
        </Card>
      </div>
    </>}
  </main>;
}
