const assert = require("node:assert/strict");
const { mkdir } = require("node:fs/promises");
const { join } = require("node:path");
const { chromium } = require("playwright-core");
const { AxeBuilder } = require("@axe-core/playwright");

const url = new URL(process.env.OPERATION_URL || "http://127.0.0.1:3000/operacao");
assert.ok(["127.0.0.1", "localhost"].includes(url.hostname), "Use uma homologação local.");

async function run() {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium" });
  const artifacts = process.env.OPERATION_SCREENSHOTS;
  if (artifacts) await mkdir(artifacts, { recursive: true });

  async function access(login, width) {
    const browserContext = await browser.newContext({ viewport: { width, height: 1000 } });
    const page = await browserContext.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.setDefaultTimeout(15000);
    const button = (name) => page.getByRole("button", { name, exact: true });
    const select = (name, value) => page.getByRole("combobox", { name, exact: true }).selectOption(value);
    const query = (fragment) => page.evaluate(async (path) => {
      const response = await fetch("/api/operacao/" + path);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }, fragment);
    async function mutate(buttonName, expectedAction, trigger = button(buttonName)) {
      const result = page.waitForResponse((response) => response.url().endsWith("/api/operacao/commands")
        && response.request().postDataJSON()?.acao === expectedAction);
      await trigger.click();
      const response = await result;
      assert.equal(response.status(), 200, await response.text());
      console.log(width, login, expectedAction);
      return response.json();
    }
    async function audit(filename) {
      const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      assert.deepEqual(violations.map((item) => item.id), []);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width);
      assert.deepEqual(errors, []);
      if (artifacts) await page.screenshot({ path: join(artifacts, filename) });
    }
    async function openLead(item) {
      await button("CRM").click();
      await page.getByLabel("Empresa ou CNPJ", { exact: true }).fill(item.razao_social);
      await button("Buscar").click();
      await page.getByRole("region", { name:"Kanban comercial" }).getByRole("button")
        .filter({ has: page.getByText(item.nome_fantasia || item.razao_social, { exact:true }) }).click();
    }
    await page.goto(url.href);
    await page.getByLabel("Usuário", { exact: true }).fill(login);
    await page.getByLabel("Senha", { exact: true }).fill("fullguete-demo");
    await button("Entrar").click();
    await page.getByRole("navigation", { name: "Módulo" }).waitFor();
    return { browserContext, page, button, select, query, audit, mutate, openLead };
  }

  try {
    const desktop = await access("bdr.ana", 1440);
    const { items } = await desktop.query("leads?view=queue&limit=100");
    const lead = items.find((item) => item.etapa === "Em contato" && item.contato_autorizado);
    assert.ok(lead);
    await desktop.button("Central BDR").click();
    await desktop.button(lead.nome_fantasia || lead.razao_social).click();
    await desktop.select("Ação na ficha", "bant");
    await desktop.select("Critério", "necessidade");
    await desktop.page.getByLabel("Valor do critério").fill("Avaliar fraude na abertura de contas");
    await desktop.mutate("Salvar ação", "bant");

    await desktop.openLead(lead);
    await desktop.page.getByRole("listbox", { name: "Soluções" }).selectOption("prospeccao_qualificada");
    await desktop.page.getByLabel("Valor mensal estimado (R$)").fill("1234.50");
    await desktop.mutate("Salvar no CRM", "oportunidade");
    await desktop.select("Ação comercial", "passagem");
    await desktop.page.getByRole("listbox", { name: "Soluções" }).selectOption("prospeccao_qualificada");
    await desktop.select("Executivo", "5");
    const future = (days) => new Date(Date.now() + days * 86400000).toISOString().slice(0, 16);
    await desktop.page.getByLabel("Horário da reunião em Brasília").fill(future(8));
    await desktop.mutate("Salvar no CRM", "passagem");
    await desktop.page.getByText("Resumo da passagem", { exact: true }).waitFor();
    await desktop.page.getByRole("heading", { name:lead.razao_social, exact:true }).scrollIntoViewIfNeeded();
    await desktop.audit("crm-desktop.png");

    await desktop.button("Consultar assistente").click();
    await desktop.button("Qual é o próximo passo?").click();
    await desktop.button("Consultar").click();
    await desktop.page.getByRole("heading", { name: "Orientação comercial" }).waitFor();
    await desktop.page.getByText(/Há retorno registrado/).waitFor();
    await desktop.audit("assistente-desktop.png");
    await desktop.browserContext.close();

    const mobile = await access("executivo", 390);
    await mobile.openLead(lead);
    await mobile.button("Agenda do lead").click();
    const meeting = mobile.page.getByRole("listitem").filter({ hasText: "Reunião comercial com executivo de contas" });
    await meeting.getByRole("button", { name: "Reagendar" }).click();
    await mobile.page.getByLabel("Novo horário de Brasília").fill(future(9));
    await mobile.mutate("Salvar horário", "agenda-reagendar");
    await mobile.audit("agenda-mobile.png");
    await mobile.mutate("Concluir", "agenda-resolver", meeting.getByRole("button", { name: "Concluir" }));
    await mobile.select("Status da agenda", "Concluído");
    await meeting.getByText(/Concluído/).waitFor();

    await mobile.button("Agenda").click();
    await mobile.button("Novo compromisso").click();
    await mobile.page.getByLabel("Empresa ou CNPJ", { exact: true }).fill(lead.razao_social);
    await mobile.button("Buscar").click();
    await mobile.select("Lead", String(lead.id));
    await mobile.page.getByLabel("Título do compromisso").fill("Registrar condições");
    await mobile.page.getByLabel("Horário de Brasília", { exact: true }).fill(future(10));
    await mobile.mutate("Agendar", "agenda-criar");
    await mobile.page.getByText("Registrar condições", { exact: true }).waitFor();

    await mobile.openLead(lead);
    for (const [stage, justification] of [["Proposta", "Proposta apresentada"], ["Ganho", "Aceite confirmado"]]) {
      await mobile.select("Ação comercial", "crm-status");
      await mobile.select("Etapa de destino", stage);
      await mobile.page.getByLabel("Justificativa comercial").fill(justification);
      await mobile.mutate("Salvar no CRM", "crm-status");
    }
    await mobile.button("Histórico").click();
    await mobile.page.getByText(/Resultado \(ganho\) enviado/).waitFor();
    await mobile.button("Analytics").click();
    await mobile.page.getByRole("heading", { name: "Conversão por etapa" }).waitFor();
    const statistics = await mobile.query("analytics?dias=0");
    assert.ok(statistics.receita.ganha >= 1234.50);
    await mobile.audit("analytics-mobile.png");
    await mobile.button("Assistente IA").click();
    await mobile.button("Onde estão os gargalos da carteira?").click();
    await mobile.button("Consultar").click();
    await mobile.page.getByText(/SLA vencidos · .* em revisão/).waitFor();
    await mobile.browserContext.close();
  } finally {
    await browser.close();
  }
}

run().catch((error) => { console.error(error); process.exitCode = 1; });
