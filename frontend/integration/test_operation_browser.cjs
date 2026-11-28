const { chromium } = require("playwright-core");
const { AxeBuilder } = require("@axe-core/playwright");
const assert = require("node:assert/strict");
const { join } = require("node:path");
const { mkdir } = require("node:fs/promises");
const url = process.env.OPERATION_URL || "http://127.0.0.1:3000/operacao";
const screenshots = process.env.OPERATION_SCREENSHOTS;
assert.ok(["127.0.0.1", "localhost"].includes(new URL(url).hostname), "Use uma homologação local.");

async function screenshot(page, filename) {
  if (!screenshots) return;
  await mkdir(screenshots, { recursive: true });
  await page.screenshot({ path: join(screenshots, filename) });
}

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium"});
  async function client(width, login) {
    const context = await browser.newContext({viewport:{width,height:1000}});
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.goto(url);
    await page.getByLabel("Usuário",{exact:true}).fill(login);
    await page.getByLabel("Senha",{exact:true}).fill("fullguete-demo");
    await page.getByRole("button",{name:"Entrar",exact:true}).click();
    await page.getByRole("heading",{name:"Leads autorizados"}).waitFor();
    const button = (name) => page.getByRole("button",{name,exact:true});
    const byRow = (name) => page.getByRole("row").filter({has:button(name)});
    const choose = async (name, value) => page.getByLabel(name,{exact:true}).selectOption(value);
    const request = (path) => page.evaluate(async p => {
      const result = await fetch("/api/operacao/"+p);
      if(!result.ok) throw Error(p+":"+result.status);
      return result.json();
    },path);
    const audit = async () => {
      const {violations}=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21a","wcag21aa"]).analyze();
      assert.deepEqual(violations.map(v=>[v.id,v.nodes.map(n=>n.target)]),[]);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
      assert.deepEqual(errors,[]);
    };
    const mutate = async (name, action) => {
      const response = page.waitForResponse(res=>res.url().endsWith("/api/operacao/commands") && res.request().method()==="POST");
      await action();
      const result = await response;
      const data = await result.json();
      assert.equal(result.status(),200,name + ": " + JSON.stringify(data));
      console.log(width,login,name);
      return data;
    };
    return {context,page,button,byRow,choose,request,audit,mutate};
  }
  try {
    const desk = await client(1440,"gestor");
    const {page,button,choose,request,audit,mutate,byRow} = desk;
    await button("Busca CNPJá simulada").click();
    for(const [name,value] of [["UF","DF"],["Código IBGE do município","5300108"],["CNAE","4711302"],["Mês de abertura","11"],["Ano de abertura","2026"]])
      await page.getByLabel(name,{exact:true}).fill(value);
    const found = await mutate("busca simulada",()=>button("Buscar empresas").click());
    await page.getByRole("checkbox",{name:/Selecionar empresa/}).nth(0).check();
    await page.getByRole("checkbox",{name:/Selecionar empresa/}).nth(1).check();
    const imported=await mutate("importação seletiva",()=>button("Importar selecionadas (2)").click());
    assert.equal(imported.criados,2);
    await page.getByText("2 importadas · 0 já existentes · 0 rejeitadas").waitFor();
    await page.getByLabel("Histórico de buscas").selectOption("");
    await page.getByLabel("Histórico de buscas").selectOption(String(found.id));
    await page.getByRole("checkbox",{name:/Selecionar empresa/}).first().check();
    assert.equal((await mutate("histórico e deduplicação",()=>button("Importar selecionadas (1)").click())).duplicados,1);
    await button("Busca CNPJá simulada").click();
    await button("Capturados").click();
    await page.getByRole("checkbox",{name:"Selecionar todos os leads da página"}).check();
    await choose("Ação em lote","processar");
    assert.equal((await mutate("classificação em lote",()=>button("Aplicar").click())).total,2);
    await page.getByText("Nenhum registro neste escopo.").waitFor();

    await button("Revisão").click();
    let row = (await request("leads?view=review")).items[0];
    await button(row.nome_fantasia||row.razao_social).click();
    await choose("Ação na ficha","revisar");
    await choose("Decisão","ajustar");
    await page.getByLabel("Justificativa da revisão").fill("Classificação confirmada pela revisão de homologação");
    await choose("Classificação","Quente");
    assert.equal((await mutate("revisão humana",()=>button("Salvar ação").click())).etapa,"Na fila do BDR");
    await page.getByText("Na fila do BDR · Score "+(row.nota_final??"—"),{exact:true}).waitFor();

    await button("Central BDR").click();
    await button("Triagem").click();
    const eligible=(await request("leads?view=triage")).items.filter(item=>item.etapa==="Em nutrição").slice(0,2);
    assert.equal(eligible.length,2);
    for(const item of eligible) await byRow(item.nome_fantasia||item.razao_social).getByRole("checkbox").check();
    await choose("Ação em lote","triagem");
    await choose("Responsável","2");
    await page.getByLabel("Justificativa",{exact:true}).fill("Encaminhamento em lote de homologação");
    assert.equal((await mutate("triagem e atribuição em lote",()=>button("Aplicar").click())).total,2);
    await byRow(eligible[0].nome_fantasia||eligible[0].razao_social).waitFor({state:"detached"});
    await button("Minha fila").click();
    // Atribui um lead visível da fila a outro BDR.
    const active=(await request("leads?view=queue")).items.find(item=>item.responsavel_id===2 && item.etapa==="Na fila do BDR");
    await byRow(active.nome_fantasia||active.razao_social).getByRole("checkbox").check();
    await choose("Ação em lote","atribuir");
    await choose("Responsável","3");
    await page.getByLabel("Justificativa",{exact:true}).fill("Redistribuição validada em homologação");
    await mutate("redistribuição",()=>button("Aplicar").click());
    assert.equal((await request("leads/"+active.id)).responsavel_id,3);
    await button(active.nome_fantasia || active.razao_social).click();
    await page.getByText("Responsável: Bruno Demo", { exact: true }).waitFor();
    await audit();
    await screenshot(page, "desktop.png");
    await desk.context.close();

    const mobile = await client(390,"bdr.ana");
    await mobile.button("Central BDR").click();
    const own=(await mobile.request("leads?view=queue")).items.find(item=>item.contato_autorizado && item.etapa==="Na fila do BDR");
    assert.ok(own);
    const name=own.nome_fantasia||own.razao_social;
    const ficha=async()=>await mobile.page.getByRole("heading",{name:own.razao_social,exact:true}).waitFor();
    await mobile.button(name).click();
    await ficha();
    await mobile.choose("Ação na ficha","bant");
    await mobile.choose("Critério","necessidade");
    await mobile.page.getByLabel("Valor do critério").fill("Entender demanda de crédito");
    await mobile.page.getByRole("checkbox",{name:"Confirmar critério"}).check();
    await mobile.mutate("BANT progressivo",()=>mobile.button("Salvar ação").click());
    await mobile.page.getByText("Confirmado",{exact:true}).waitFor();
    await mobile.choose("Ação na ficha","atividade");
    await mobile.choose("Tipo de atividade","Ligação");
    await mobile.choose("Resultado","Sem resposta");
    await mobile.mutate("registro de atividade",()=>mobile.button("Salvar ação").click());
    await mobile.page.getByText("Em contato · Score "+(own.nota_final??"—"),{exact:true}).waitFor();
    await mobile.mutate("cadência",()=>mobile.page.getByRole("button",{name:"Marcar concluído",exact:true}).first().click());
    await mobile.choose("Ação na ficha","retorno");
    await mobile.page.getByLabel("Título do retorno").fill("Ligar novamente");
    const date = new Date(Date.now()+48*3600*1000).toISOString().slice(0,16);
    await mobile.page.getByLabel("Data e hora de Brasília").fill(date);
    await mobile.mutate("agendamento de retorno",()=>mobile.button("Salvar ação").click());
    await mobile.page.getByText(/^Retorno:/).waitFor();
    await mobile.audit();
    await mobile.page.getByRole("heading",{name:"Ficha do lead"}).evaluate((heading) => heading.scrollIntoView());
    await screenshot(mobile.page, "mobile.png");

    await mobile.byRow(name).getByRole("checkbox").check();
    await mobile.choose("Ação em lote","status");
    await mobile.choose("Novo status","Perdido");
    await mobile.page.getByLabel("Justificativa",{exact:true}).fill("Lead pediu encerramento da negociação.");
    await mobile.choose("Motivo","Outro");
    await mobile.mutate("alteração de status com justificativa",()=>mobile.button("Aplicar").click());
    await mobile.byRow(name).waitFor({state:"detached"});
    await mobile.page.getByText("Perdido · Score "+(own.nota_final??"—"),{exact:true}).waitFor();
    const toDiscard = (await mobile.request("leads?view=queue")).items.find((item) => item.etapa === "Na fila do BDR");
    assert.ok(toDiscard);
    const discardName = toDiscard.nome_fantasia || toDiscard.razao_social;
    await mobile.byRow(discardName).getByRole("checkbox").check();
    await mobile.choose("Ação em lote", "status");
    await mobile.choose("Novo status", "Descartado");
    await mobile.page.getByLabel("Justificativa", { exact: true }).fill("Empresa sem aderência à oferta.");
    await mobile.choose("Motivo", "Sem fit");
    await mobile.mutate("descarte com justificativa", () => mobile.button("Aplicar").click());
    await mobile.byRow(discardName).waitFor({ state: "detached" });
    assert.equal((await mobile.request("leads/" + toDiscard.id)).etapa, "Descartado");
    await mobile.context.close();
  } finally {
    await browser.close();
  }
})().catch(error=>{ console.error(error);process.exitCode=1; });
