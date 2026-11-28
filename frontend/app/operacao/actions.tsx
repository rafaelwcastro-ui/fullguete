"use client";

import { useState, type FormEvent } from "react";
import { bantLabels, control, formatDate, primary, target, type BantField, type Command, type Lead, type Options } from "./contracts";

type Submit = (command: Command) => void;
const activities = ["Nota", "Ligação", "E-mail", "WhatsApp", "Reunião"];

function Select({ name, label, values, optional = false, onChange }: {
  name: string; label: string; values: string[]; optional?: boolean; onChange?: (value: string) => void;
}) {
  return <label className="flex min-w-0 flex-col gap-1 text-sm">
    {label}<select name={name} aria-label={label} className={control} required={!optional} defaultValue="" onChange={(event) => onChange?.(event.target.value)}>
      <option value="">{optional ? "Manter atual" : "Selecionar"}</option>
      {values.map((value) => <option key={value}>{value}</option>)}
    </select>
  </label>;
}

function Text({ name, label, min = 0, max = 500 }: { name: string; label: string; min?: number; max?: number }) {
  return <label className="flex min-w-0 flex-col gap-1 text-sm">
    {label}<input name={name} className={control} minLength={min} maxLength={max} required={min > 0} />
  </label>;
}

export function BatchActions({ leads, options, manager, pending, submit }: {
  leads: Lead[]; options: Options; manager: boolean; pending: boolean; submit: Submit;
}) {
  const [action, setAction] = useState("");
  const [stage, setStage] = useState("");
  if (!leads.length) return null;
  const stages = (options.estado[leads[0].etapa] ?? []).filter(
    (stage) => leads.every((lead) => options.estado[lead.etapa]?.includes(stage)),
  );
  const actions = [
    ...(stages.length ? [{ id: "status", name: "Alterar status" }] : []),
    ...(manager && leads.every((lead) => options.processaveis.includes(lead.etapa))
      ? [{ id: "processar", name: "Processar com IA" }] : []),
    ...(manager && leads.every((lead) => options.triagem.includes(lead.etapa))
      ? [{ id: "triagem", name: "Encaminhar à fila" }] : []),
    ...(manager && leads.every((lead) => Object.hasOwn(options.estado, lead.etapa))
      ? [{ id: "atribuir", name: "Atribuir responsável" }] : []),
  ];
  const selectedAction = actions.some(({ id }) => id === action) ? action : "";

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const selection = leads.map(target);
    if (selectedAction === "status") {
      submit({
        acao: action, leads: selection, etapa: stage, justificativa: fields.get("justificativa"),
        motivo: fields.get("motivo") || null, canal: fields.get("canal") || "", resultado: fields.get("resultado") || "",
      });
    } else if (selectedAction === "triagem" || selectedAction === "atribuir") {
      submit({ acao: action, leads: selection, bdr: Number(fields.get("bdr")), motivo: fields.get("motivo") });
    } else if (selectedAction === "processar") {
      submit({ acao: action, leads: selection });
    }
  }

  return <form onSubmit={apply} className="mt-3 rounded-lg border border-border bg-background p-3">
    <fieldset disabled={pending} className="flex flex-wrap items-end gap-3">
      <legend className="px-1 text-sm text-muted">{leads.length} lead(s) selecionado(s)</legend>
      <label className="flex flex-col gap-1 text-sm">Ação em lote
        <select aria-label="Ação em lote" className={control} value={selectedAction} onChange={(event) => { setAction(event.target.value); setStage(""); }} required>
          <option value="">Selecionar</option>
          {actions.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}
        </select>
      </label>
      {selectedAction === "status" && <>
        <Select name="stage" label="Novo status" values={stages} onChange={setStage} />
        <Text name="justificativa" label="Justificativa" min={8} />
        {["Descartado", "Perdido"].includes(stage) && <Select name="motivo" label="Motivo" values={options.motivos} />}
        {stage === "Em contato" && <>
          <Select name="canal" label="Canal" values={activities.slice(1, 4)} />
          <Select name="resultado" label="Resultado do contato" values={options.resultados} />
        </>}
      </>}
      {["triagem", "atribuir"].includes(selectedAction) && <>
        <label className="flex flex-col gap-1 text-sm">Responsável
          <select name="bdr" aria-label="Responsável" className={control} defaultValue="" required>
            <option value="">Selecionar BDR</option>
            {options.bdrs.map((bdr) => <option key={bdr.id} value={bdr.id}>{bdr.nome}</option>)}
          </select>
        </label>
        <Text name="motivo" label="Justificativa" min={10} />
      </>}
      <button className={primary} disabled={!selectedAction || pending}>{pending ? "Aplicando…" : "Aplicar"}</button>
    </fieldset>
  </form>;
}

export function LeadActions({ lead, options, manager, pending, submit }: {
  lead: Lead; options: Options; manager: boolean; pending: boolean; submit: Submit;
}) {
  const [action, setAction] = useState("");
  const [decision, setDecision] = useState("");
  const [activity, setActivity] = useState("Nota");
  const run = (command: Command) => submit({ ...command, leads: [target(lead)] });

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    if (action === "bant") {
      const field = String(fields.get("criterio")) as BantField;
      run({ acao: "bant", valores: { [field]: fields.get("valor") }, confirmacoes: { [field]: fields.has("confirmado") } });
    } else if (action === "atividade") {
      run({ acao: "atividade", tipo: activity, resultado: fields.get("resultado") || "", anotacao: fields.get("anotacao"),
        proxima_acao: fields.get("proxima_acao") });
    } else if (action === "retorno") {
      run({ acao: "retorno", titulo: fields.get("titulo"), inicio: fields.get("inicio") });
    } else if (action === "revisar") {
      run({ acao: "revisar", decisao: decision, motivo: fields.get("motivo"), classificacao: fields.get("classificacao") || null,
        solucao: fields.get("solucao") || null, motivo_descarte: fields.get("descarte") || null });
    }
  }

  return <>
    <form onSubmit={apply} className="mt-4 border-t border-border pt-4">
      <fieldset className="grid gap-3" disabled={pending}>
        <label className="flex flex-col gap-1 text-sm">Ação na ficha
          <select aria-label="Ação na ficha" value={action} onChange={(event) => setAction(event.target.value)} className={control} required>
            <option value="">Selecionar</option>
            {manager && lead.etapa === "Revisão humana" && <option value="revisar">Registrar decisão de revisão</option>}
            <option value="bant">Atualizar critério BANT</option>
            <option value="atividade">Registrar atividade</option>
            {lead.contato_autorizado && <option value="retorno">Agendar retorno</option>}
          </select>
        </label>
        {action === "bant" && <>
          <label className="flex flex-col gap-1 text-sm">Critério
            <select name="criterio" aria-label="Critério" className={control} required>
              {Object.entries(bantLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          <Text name="valor" label="Valor do critério" max={200} />
          <label className="text-sm"><input name="confirmado" type="checkbox" /> Confirmar critério</label>
        </>}
        {action === "atividade" && <>
          <label className="flex flex-col gap-1 text-sm">Tipo de atividade
            <select aria-label="Tipo de atividade" value={activity} onChange={(event) => setActivity(event.target.value)} className={control}>
              {(lead.contato_autorizado ? activities : activities.slice(0, 1)).map((kind) => <option key={kind}>{kind}</option>)}
            </select>
          </label>
          {activity !== "Nota" && <Select name="resultado" label="Resultado" values={options.resultados} />}
          <Text name="anotacao" label="Anotação" min={activity === "Nota" ? 1 : 0} max={1000} />
          <Text name="proxima_acao" label="Próxima ação" max={180} />
        </>}
        {action === "retorno" && <>
          <Text name="titulo" label="Título do retorno" min={4} max={180} />
          <label className="flex flex-col gap-1 text-sm">Data e hora de Brasília
            <input name="inicio" type="datetime-local" required className={control} />
          </label>
        </>}
        {action === "revisar" && <>
          <label className="flex flex-col gap-1 text-sm">Decisão
            <select aria-label="Decisão" className={control} value={decision} onChange={(event) => setDecision(event.target.value)} required>
              <option value="">Selecionar</option><option value="aprovar">Aprovar</option>
              <option value="ajustar">Ajustar</option><option value="descartar">Descartar</option>
            </select>
          </label>
          <Text name="motivo" label="Justificativa da revisão" min={1} />
          {decision === "ajustar" && <>
            <Select name="classificacao" label="Classificação" values={options.classificacoes} />
            <label className="flex flex-col gap-1 text-sm">Solução
              <select name="solucao" aria-label="Solução" className={control} defaultValue=""><option value="">Manter atual</option>
                {options.solucoes.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
              </select>
            </label>
          </>}
          {decision === "descartar" && <Select name="descarte" label="Motivo do descarte" values={options.motivos} />}
        </>}
        {action && <button className={primary} disabled={pending}>{pending ? "Salvando…" : "Salvar ação"}</button>}
      </fieldset>
    </form>
    {!!lead.cadencia?.length && <section className="mt-4 border-t border-border pt-4">
      <h3 className="font-semibold">Cadência</h3>
      <ul className="mt-2 space-y-2 text-sm">
        {lead.cadencia.map((step) => <li key={step.id} className="flex flex-wrap items-center justify-between gap-2">
          <span>{step.canal} · {formatDate(step.previsto_para)}</span>
          <button type="button" disabled={pending} className={control} aria-pressed={!!step.feito_em}
            onClick={() => run({ acao: "cadencia", passo: step.id, feito: !step.feito_em })}>
            {step.feito_em ? "Concluído" : "Marcar concluído"}
          </button>
        </li>)}
      </ul>
    </section>}
  </>;
}
