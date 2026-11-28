import snapshot from "./demo-dashboard.json";

export const series = snapshot.series;

export const queue = [
 {id:"DEMO-01",empresa:"Empresa exemplo A",segmento:"Varejo",campanha:"Varejo",etapa:"Reunião marcada",agenda:"27/11/2026, 14h",score:94,status:"Aguardando avaliação",acao:"Revisar recomendação"},
 {id:"DEMO-02",empresa:"Empresa exemplo B",segmento:"Distribuição",campanha:"Expansão B2B",etapa:"Qualificado",agenda:null,score:88,status:"Em análise",acao:"Validar necessidade"},
 {id:"DEMO-03",empresa:"Empresa exemplo C",segmento:"Serviços",campanha:"Expansão B2B",etapa:null,agenda:null,score:82,status:"Base legal pendente",acao:"Validar base legal"},
 {id:"DEMO-04",empresa:"Empresa exemplo D",segmento:"Indústria",campanha:"Expansão B2B",etapa:"Em contato",agenda:null,score:76,status:"Em análise",acao:"Revisar classificação"},
];
