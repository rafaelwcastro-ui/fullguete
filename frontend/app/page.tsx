"use client";
import { useMemo, useState } from "react";
import { Activity, ArrowDownRight, ArrowRight, CalendarDays, ChartNoAxesCombined, CircleHelp, LayoutDashboard, ListTodo, Rocket, Search, Settings, ShieldCheck, Target, Users, Workflow } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "@/components/ui/card";
import { queue, series } from "@/lib/demo";

const nav = [
 {name:"Visão geral",icon:LayoutDashboard,href:"#inicio"},
 {name:"Prospecção",icon:Target,href:null},
 {name:"Central de trabalho",icon:ListTodo,href:"#central"},
 {name:"CRM",icon:Workflow,href:"#pipeline"},
 {name:"Analytics",icon:ChartNoAxesCombined,href:"#evolucao"},
 {name:"Administração",icon:Settings,href:null},
];
const fmt = new Intl.NumberFormat("pt-BR");
export default function Dashboard() {
 const [period,setPeriod] = useState<"7"|"30">("30");
 const [search,setSearch] = useState("");
 const [active,setActive] = useState("#inicio");
 const data = period === "7" ? series.slice(-3) : series;
 const totals = data.reduce((a,r)=>({capturados:a.capturados+r.capturados,tratados:a.tratados+r.tratados,qualificados:a.qualificados+r.qualificados,reunioes:a.reunioes+r.reunioes}),{capturados:0,tratados:0,qualificados:0,reunioes:0});
 const stats = [
  {label:"Leads capturados",value:totals.capturados,icon:Users,note:"Entrada de oportunidades"},
  {label:"Tratados pela IA",value:totals.tratados,icon:Activity,note:"Classificação interna"},
  {label:"Qualificados",value:totals.qualificados,icon:Target,note:"Potencial comercial"},
  {label:"Reuniões",value:totals.reunioes,icon:CalendarDays,note:"Avanço do funil"},
 ];
 const visible = useMemo(()=>queue.filter(r=>[r.empresa,r.segmento,r.status].join(" ").toLowerCase().includes(search.toLowerCase().trim())),[search]);
 return <div className="min-h-screen lg:grid lg:grid-cols-[244px_minmax(0,1fr)]">
  <aside className="border-b border-border bg-[#0d1420] px-4 py-5 lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:border-b-0 lg:border-r lg:px-5 lg:py-8">
   <a href="#inicio" onClick={()=>setActive("#inicio")} className="flex items-center gap-3 px-2">
    <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-primary to-secondary text-background"><Rocket size={23}/></span>
    <span><span className="block text-xl font-bold tracking-tight">fullguete<span className="text-primary">.</span></span><span className="block text-[10px] tracking-wide text-muted">Inteligência comercial</span></span>
   </a>
   <p className="mb-3 mt-9 hidden px-3 text-[10px] font-semibold uppercase tracking-[.2em] text-muted lg:block">Workspace</p>
   <nav aria-label="Navegação da prévia" className="mt-5 flex gap-1 overflow-x-auto lg:mt-0 lg:flex-col lg:overflow-visible">
    {nav.map(({name,icon:Icon,href})=>href?
     <a key={name} href={href} onClick={()=>setActive(href)} className={"flex shrink-0 items-center gap-3 whitespace-nowrap rounded-lg px-3 py-3 text-sm transition "+(active===href?"bg-[#193b3b] font-semibold text-primary":"text-muted hover:bg-card hover:text-foreground")} aria-current={active===href?"location":undefined}><Icon size={18}/>{name}</a>:
     <span key={name} title="Módulo previsto; não integrado nesta prévia" className="flex shrink-0 items-center gap-3 whitespace-nowrap rounded-lg px-3 py-3 text-sm text-muted opacity-60"><Icon size={18}/>{name}</span>)}
   </nav>
   <div className="mt-auto hidden rounded-xl border border-border p-3 text-xs leading-relaxed text-muted lg:block"><div className="mb-1 flex items-center gap-2 font-semibold text-foreground"><ShieldCheck size={15} className="text-primary"/> Ambiente de design</div>Dados fictícios. Operação atual preservada.</div>
  </aside>
  <main id="inicio" className="mx-auto w-full max-w-[1600px] min-w-0 space-y-6 px-4 py-6 sm:px-7 lg:px-8 lg:py-8">
   <header className="flex flex-wrap items-center justify-between gap-4">
    <div><p className="text-xs font-medium text-muted">Workspace / Visão geral</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Visão geral</h1></div>
    <div className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-2 text-xs text-muted"><span className="h-2 w-2 rounded-full bg-primary"/> Prévia · dados ilustrativos</div>
   </header>
   <section className="hero flex flex-wrap items-center justify-between gap-5 rounded-2xl border border-border px-6 py-6">
    <div><p className="text-xs font-semibold uppercase tracking-[.16em] text-primary">Seu centro de inteligência comercial</p><h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">Da oportunidade à conversão.</h2><p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">Acompanhe a geração de leads, entenda o pipeline e concentre a equipe nas próximas ações.</p></div>
    <a href="#central" onClick={()=>setActive("#central")} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-background">Ver fila de exemplo <ArrowRight size={16}/></a>
   </section>
   <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">Desempenho comercial</h2><div role="group" aria-label="Período ilustrativo" className="flex rounded-lg border border-border bg-card p-1">{(["7","30"] as const).map(p=><button key={p} aria-pressed={p===period} onClick={()=>setPeriod(p)} className={"rounded-md px-3 py-2 text-xs font-medium "+(p===period?"bg-[#244044] text-primary":"text-muted hover:text-foreground")}>{p} dias</button>)}</div></div>
   <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{stats.map(({label,value,icon:Icon,note})=><Card key={label}><div className="flex items-center justify-between gap-2 text-sm text-muted"><span>{label}</span><span className="rounded-lg bg-[#193238] p-2 text-primary"><Icon size={18}/></span></div><div className="mt-3 text-3xl font-semibold tracking-tight tabular-nums">{fmt.format(value)}</div><p className="mt-2 text-xs text-muted">{note}</p></Card>)}</div>
   <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
    <Card id="evolucao" className="panel-scroll min-w-0"><h2 className="font-semibold">Evolução da prospecção</h2><p className="mt-1 text-xs text-muted">Volume ilustrativo no período</p><div className="mt-4 flex gap-4 text-xs text-muted"><span><span className="mr-2 inline-block h-2 w-2 rounded-full bg-primary"/>Capturados</span><span><span className="mr-2 inline-block h-2 w-2 rounded-full bg-secondary"/>Tratados</span></div>
     <div className="mt-4 h-[230px] min-w-0" aria-label="Gráfico de evolução de leads"><ResponsiveContainer width="100%" height="100%" minWidth={0}><AreaChart data={data} margin={{left:-18,right:10,top:10,bottom:0}}><defs><linearGradient id="leadFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#62e4cb" stopOpacity={.24}/><stop offset="100%" stopColor="#62e4cb" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#263343" vertical={false} strokeDasharray="3 5"/><XAxis dataKey="day" axisLine={false} tickLine={false} tick={{fill:"#a1afc0",fontSize:11}}/><YAxis axisLine={false} tickLine={false} tick={{fill:"#a1afc0",fontSize:11}}/><Tooltip contentStyle={{background:"#111925",border:"1px solid #263343",borderRadius:12,color:"#edf3f7"}}/><Area name="Capturados" dataKey="capturados" type="monotone" stroke="#62e4cb" strokeWidth={2.5} fill="url(#leadFill)" isAnimationActive={false}/><Area name="Tratados" dataKey="tratados" type="monotone" stroke="#53c9ec" strokeWidth={2} fill="transparent" isAnimationActive={false}/></AreaChart></ResponsiveContainer></div>
    </Card>
    <Card id="pipeline" className="panel-scroll"><div className="flex items-center justify-between"><h2 className="font-semibold">Pipeline comercial</h2><ArrowDownRight className="text-primary" size={20}/></div><p className="mt-1 text-xs text-muted">Avanço em relação à captura</p><div className="mt-6 space-y-5">{stats.map(({label,value})=>{const percent=totals.capturados?Math.round(value/totals.capturados*100):0;return <div key={label}><div className="mb-2 flex items-center justify-between text-xs"><span className="text-muted">{label}</span><span className="tabular-nums">{value} · {percent}%</span></div><div className="h-2 overflow-hidden rounded-full bg-[#253342]"><div className="h-full rounded-full bg-gradient-to-r from-primary to-secondary" style={{width:percent+"%"}}/></div></div>})}</div><p className="mt-6 border-t border-border pt-4 text-xs leading-relaxed text-muted">Indicadores ilustrativos, sem inferência de probabilidade real.</p></Card>
   </div>
   <Card id="central" className="panel-scroll min-w-0"><div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="font-semibold">Próximas ações</h2><p className="mt-1 text-xs text-muted">Amostra da central de trabalho · não vinculada ao período</p></div><label className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-muted"><Search size={16}/><input aria-label="Buscar empresa de exemplo" placeholder="Buscar empresa..." value={search} onChange={e=>setSearch(e.target.value)} className="w-40 bg-transparent text-sm text-foreground outline-none placeholder:text-muted sm:w-52"/></label></div>
    <div className="mt-5 overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><thead className="border-b border-border text-[11px] uppercase tracking-wider text-muted"><tr>{["Empresa","Segmento","Score IA","Situação","Próxima ação"].map(x=><th key={x} className="px-2 py-3 font-medium" scope="col">{x}</th>)}</tr></thead><tbody>{visible.map(r=><tr key={r.id} className="border-b border-border last:border-0"><td className="px-2 py-4 font-medium">{r.empresa}</td><td className="px-2 py-4 text-muted">{r.segmento}</td><td className="px-2 py-4 font-semibold tabular-nums text-primary">{r.score}</td><td className="px-2 py-4"><span className={"whitespace-nowrap rounded-full px-2 py-1 text-xs "+(r.status==="Base legal pendente"?"bg-[#3b2f20] text-[#f5ce91]":"bg-[#263544] text-foreground")}>{r.status}</span></td><td className="px-2 py-4 text-muted">{r.acao}</td></tr>)}</tbody></table>{visible.length===0&&<p className="py-6 text-center text-sm text-muted">Nenhum exemplo encontrado.</p>}</div>
   </Card>
   <footer className="flex items-center gap-2 pb-4 text-xs text-muted"><CircleHelp size={15}/> Prévia visual independente. Nenhuma consulta, alteração de lead ou integração externa é executada.</footer>
  </main>
 </div>;
}
