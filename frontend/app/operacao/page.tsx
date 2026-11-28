"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { CompanySearch } from "./company-search";
import { Card } from "@/components/ui/card";

type User={id:number;nome:string;papel:"gestor"|"bdr"|"executivo"};
type Campaign={id:number;tag:string;importados_visiveis:number};
const bantLabels = {orcamento:"Orçamento",autoridade:"Autoridade",necessidade:"Necessidade",prazo:"Prazo"};
type BantStatus = {preenchido:boolean;confirmado:boolean};
type Cadence = {dia:number;canal:string;previsto_para:string;feito_em:string|null};
type Lead={id:number;razao_social:string;nome_fantasia:string|null;cnpj:string|null;segmento:string|null;etapa:string;nota_final:number|null;solucao_principal:string|null;base_contato:string;contato_autorizado:boolean;base_ficticia:boolean;campanhas?:{id:number;tag:string}[];bant?:Record<keyof typeof bantLabels,BantStatus>;cadencia?:Cadence[]};
type List={items:Lead[];total:number};
type View="all"|"queue"|"triage"|"review";

async function api<T>(path:string, init?:RequestInit):Promise<T> {
 const res=await fetch("/api/operacao/"+path,{...init,cache:"no-store",credentials:"same-origin"});
 if(!res.ok) {
  const body=await res.json().catch(()=>({}));
  throw Object.assign(new Error(body.detail||"Falha na consulta."),{status:res.status});
 }
 return res.json();
}

export default function Operacao() {
 const [user,setUser]=useState<User|null>(null);
 const [checking,setChecking]=useState(true);
 const [login,setLogin]=useState("");
 const [password,setPassword]=useState("");
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState("");
 const [view,setView]=useState<View>("all");
 const [module,setModule]=useState<"prospecting"|"work">("prospecting");
 const [campaign,setCampaign]=useState("");
 const [campaigns,setCampaigns]=useState<Campaign[]>([]);
 const [offset,setOffset]=useState(0);
 const [list,setList]=useState<List|null>(null);
 const [detail,setDetail]=useState<Lead|null>(null);
 const [loading,setLoading]=useState(false);
 const [selected,setSelected]=useState<number|null>(null);
 const reset=()=>{setUser(null);setList(null);setDetail(null);setCampaigns([]);setSelected(null);setCampaign("");setOffset(0)};
 useEffect(()=>{
  let current=true;
  api<User>("me").then(u=>{if(current)setUser(u)}).catch(e=>{if(current&&e.status!==401)setError(e.message)}).finally(()=>{if(current)setChecking(false)});
  return ()=>{current=false};
 },[]);
 useEffect(()=>{
  if(!user)return;
  let current=true;
  api<{items:Campaign[]}>("campaigns?limit=100").then(r=>{if(current)setCampaigns(r.items)}).catch(e=>{if(current){setError(e.message);if(e.status===401)setUser(null)}});
  return ()=>{current=false};
 },[user]);
 useEffect(()=>{
  if(!user)return;
  let current=true;
  setLoading(true);setList(null);setDetail(null);setSelected(null);setError("");
  const query=new URLSearchParams({view,limit:"30",offset:String(offset)});
  if(campaign)query.set("campaign_id",campaign);
  api<List>("leads?"+query.toString()).then(r=>{if(current)setList(r)}).catch(e=>{if(current){setError(e.message);if(e.status===401)setUser(null)}}).finally(()=>{if(current)setLoading(false)});
  return ()=>{current=false};
 },[user,view,campaign,offset,module]);
 useEffect(()=>{
  if(!user||selected===null)return;
  let current=true;setDetail(null);
  api<Lead>("leads/"+selected).then(r=>{if(current)setDetail(r)}).catch(e=>{if(current){setError(e.message);if(e.status===401)setUser(null)}});
  return ()=>{current=false};
 },[user,selected]);
 async function signIn(e:FormEvent<HTMLFormElement>) {
  e.preventDefault();setBusy(true);setError("");reset();
  try{const r=await api<{usuario:User}>("session",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({login,senha:password})});setUser(r.usuario);setView("all");setModule("prospecting");}
  catch(e){setError(e instanceof Error?e.message:"Não foi possível entrar.")}
  finally{setBusy(false);setPassword("")}
 }
 async function signOut(){
  setBusy(true);
  try{await api("session",{method:"DELETE"});setError("")}
  catch(e){setError(e instanceof Error?e.message:"Revogação não confirmada.")}
  finally{reset();setBusy(false)}
 }
 function changeModule(next:"prospecting"|"work") {setModule(next);setView(next==="work"&&user?.papel!=="executivo"?"queue":"all");setOffset(0);setSelected(null);setDetail(null)}
 const filters: [View,string][] = module==="prospecting"?[["all","Empresas"],["review","Revisão"]]:[...(user?.papel!=="executivo"?[["queue","Minha fila"] as [View,string]]:[]),["all","Todos os leads"],...(user?.papel==="gestor"?[["triage","Triagem"] as [View,string]]:[])];
 const bant = detail?.bant;
 return <main className="mx-auto min-h-screen max-w-6xl space-y-5 p-4 sm:p-8">
  <header className="flex flex-wrap items-center justify-between gap-4"><Image src="/logo.png" alt="Fullguete" width={164} height={43} unoptimized/><Link href="/" className="text-sm text-muted underline">Voltar à prévia</Link></header>
  <section className="metric-panel rounded-2xl border border-border p-5"><p className="text-xs font-semibold text-primary">Homologação local · somente leitura</p><h1 className="mt-2 text-2xl font-semibold">Prospecção e Central BDR</h1><p className="mt-2 text-sm text-muted">A carteira local usa dados fictícios e escopo definido no servidor. O gestor pode consultar o provedor quando configurado.</p></section>
  {checking?<p role="status" className="text-muted">Verificando sessão...</p>:!user?<Card className="mx-auto max-w-md"><h2 className="font-semibold">Acesso à API local</h2><form onSubmit={signIn} className="mt-4 space-y-4"><label className="block text-sm">Usuário<input required autoComplete="username" value={login} onChange={e=>setLogin(e.target.value)} className="mt-1 block w-full rounded-lg border border-border bg-background p-3"/></label><label className="block text-sm">Senha<input required autoComplete="current-password" type="password" value={password} onChange={e=>setPassword(e.target.value)} className="mt-1 block w-full rounded-lg border border-border bg-background p-3"/></label><button disabled={busy} className="nav-active w-full rounded-lg p-3 font-semibold disabled:opacity-50">Entrar</button></form></Card>:<>
  <Card className="flex flex-wrap items-center justify-between gap-3"><div><strong>{user.nome}</strong><p className="text-xs text-muted">{user.papel}</p></div><button disabled={busy} type="button" onClick={signOut} className="rounded-lg border border-border px-4 py-2 text-sm">Sair</button></Card>
  <nav className="flex flex-wrap gap-2" aria-label="Módulo">{(["prospecting","work"] as const).map(m=><button key={m} onClick={()=>changeModule(m)} aria-pressed={module===m} className={"rounded-lg px-4 py-3 text-sm "+(module===m?"nav-active font-semibold":"border border-border bg-card")}>{m==="work"?"Central BDR":"Prospecção"}</button>)}</nav>
  {module==="prospecting"&&user.papel==="gestor"&&<CompanySearch key={user.id} onExpired={()=>{reset();setError("Sessão expirada.")}}/>}
  <Card><div className="flex flex-wrap gap-2">{filters.map(([v,label])=><button key={v} onClick={()=>{setView(v);setOffset(0)}} aria-pressed={v===view} className={"rounded-lg px-3 py-2 text-sm "+(v===view?"nav-active":"border border-border")}>{label}</button>)}</div>
   <div className="mt-4 text-sm"><label htmlFor="operation-campaign">Campanha</label><select id="operation-campaign" value={campaign} onChange={e=>{setCampaign(e.target.value);setOffset(0)}} className="mt-1 block w-full rounded-lg border border-border bg-background p-3 sm:w-auto"><option value="">Todas as campanhas visíveis</option>{campaigns.map(c=><option key={c.id} value={c.id}>{c.tag} ({c.importados_visiveis})</option>)}</select></div>
  </Card>
  <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]"><Card><h2 className="font-semibold">Leads autorizados</h2>{loading?<p role="status" className="mt-3 text-sm text-muted">Carregando...</p>:list?<><p className="mt-2 text-xs text-muted">{list.total} registro(s)</p><div className="mt-3 divide-y divide-border">{list.items.map(l=><button key={l.id} type="button" aria-pressed={selected===l.id} onClick={()=>setSelected(l.id)} className="flex w-full flex-wrap justify-between gap-2 rounded px-2 py-3 text-left hover:bg-white/5 aria-pressed:bg-white/10"><span className="min-w-0 break-words"><strong className="text-sm">{l.nome_fantasia||l.razao_social}</strong><span className="block text-xs text-muted">{l.etapa} · {l.base_contato==="pendente"?"Base legal pendente":"Base legal registrada"}</span></span><span className="text-sm text-primary">{l.nota_final??"—"}</span></button>)}{!list.items.length&&<p className="py-4 text-sm text-muted">Nenhum registro neste escopo.</p>}</div><div className="mt-4 flex gap-3"><button disabled={!offset} onClick={()=>setOffset(o=>Math.max(0,o-30))} className="rounded border border-border p-2 text-sm disabled:opacity-40">Anterior</button><button disabled={offset+30>=list.total} onClick={()=>setOffset(o=>o+30)} className="rounded border border-border p-2 text-sm disabled:opacity-40">Próxima</button></div></>:null}</Card>
  <Card><h2 className="font-semibold">Ficha do lead</h2>{detail?<div className="mt-4 space-y-2 text-sm break-words"><h3 className="font-semibold">{detail.razao_social}</h3><p>CNPJ: {detail.cnpj||"Não informado"}</p><p>Segmento: {detail.segmento||"Não informado"}</p><p>Etapa: {detail.etapa}</p><p>Score: {detail.nota_final??"—"}</p><p>Solução: {detail.solucao_principal||"Pendente"}</p><p>Campanhas: {detail.campanhas?.map(c=>c.tag).join(", ")||"Sem vínculo"}</p><p className="text-primary">{detail.contato_autorizado?"Base e etapa permitem contato no legado. Nenhuma ação habilitada aqui.":"Contato bloqueado pela base legal ou etapa."}</p>{bant&&<section className="mt-5 border-t border-border pt-4">
    <h4 className="font-semibold">BANT progressivo</h4>
    <dl className="mt-2 space-y-1">{(Object.keys(bantLabels) as (keyof typeof bantLabels)[]).map(field=><div key={field} className="flex flex-wrap justify-between gap-2"><dt>{bantLabels[field]}</dt><dd className="text-muted">{bant[field].confirmado?"Confirmado":bant[field].preenchido?"Preenchido":"Pendente"}</dd></div>)}</dl>
   </section>}{detail.cadencia&&detail.contato_autorizado&&<section className="mt-5 border-t border-border pt-4">
    <h4 className="font-semibold">Cadência</h4>
    {detail.cadencia.length?<ul className="mt-2 space-y-2">{detail.cadencia.map((step,index)=><li key={index}>Dia {step.dia} · {step.canal} · {step.feito_em?"Concluído":"Pendente"}</li>)}</ul>:<p className="mt-2 text-muted">Sem passos registrados.</p>}
   </section>}</div>:<p className="mt-3 text-sm text-muted">Selecione um lead autorizado.</p>}</Card></div>
  </>}
  {error&&<p role="alert" className="rounded-lg border border-border bg-card p-4 text-sm text-[#f5ce91]">{error}</p>}
 </main>
}
