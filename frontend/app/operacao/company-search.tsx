"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Card } from "@/components/ui/card";
import { api, control, primary, type RunCommand } from "./contracts";

type Company = { cnpj: string; razao_social: string; cidade: string; uf: string; cnae: string; data_abertura: string };
type SearchResult = { id?: number; tag?: string; items: Company[] };
type History = { id: number; tag: string };
const fields = [
  { name: "uf", label: "UF", pattern: "[A-Za-z]{2}" },
  { name: "municipio_ibge", label: "Código IBGE do município", pattern: "[0-9]{7}" },
  { name: "cnae", label: "CNAE", pattern: "[0-9]{7}" },
  { name: "mes", label: "Mês de abertura", pattern: "(0?[1-9]|1[0-2])" },
  { name: "ano", label: "Ano de abertura", pattern: "(20[0-9]{2}|2100)" },
];

export function CompanySearch({ writable, pending, run, onError }: {
  writable: boolean; pending: boolean; run: RunCommand; onError: (failure: unknown) => void;
}) {
  const [result, setResult] = useState<SearchResult | null>(null);
  const [selection, setSelection] = useState<string[]>([]);
  const [history, setHistory] = useState<History[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState("");
  const busy = pending || loading;

  useEffect(() => {
    if (!writable || !open) return;
    const controller = new AbortController();
    api<{ items: History[] }>("search-history", { signal: controller.signal })
      .then(({ items }) => setHistory(items))
      .catch((error) => { if (!controller.signal.aborted) onError(error); });
    return () => controller.abort();
  }, [writable, open, onError]);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const filters = {
      uf: String(form.get("uf")).toUpperCase(), municipio_ibge: Number(form.get("municipio_ibge")),
      ano: Number(form.get("ano")), mes: Number(form.get("mes")), cnae: String(form.get("cnae")),
    };
    setLoading(true);
    setFeedback("");
    try {
      const current = writable
        ? await run<SearchResult>({ acao: "buscar", ...filters })
        : await api<SearchResult>("company-search", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(filters),
        });
      setResult(current);
      setSelection([]);
      if (current.id && current.tag) {
        const record = { id: current.id, tag: current.tag };
        setHistory((previous) => [record, ...previous.filter((item) => item.id !== record.id)]);
      }
    } catch (failure) { onError(failure); }
    finally { setLoading(false); }
  }

  async function loadHistory(id: string) {
    if (!id) { setResult(null); setSelection([]); return; }
    setLoading(true);
    setFeedback("");
    try {
      setResult(await api<SearchResult>("search-history/" + id));
      setSelection([]);
    } catch (error) { onError(error); }
    finally { setLoading(false); }
  }

  async function importSelected() {
    if (!result?.id) return;
    try {
      const counts = await run<{ criados: number; duplicados: number; rejeitados: number }>({
        acao: "importar", campanha: result.id, cnpjs: selection,
      });
      setFeedback(`${counts.criados} importadas · ${counts.duplicados} já existentes · ${counts.rejeitados} rejeitadas`);
      setSelection([]);
    } catch (error) { onError(error); }
  }

  return <Card>
    <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
      className="flex w-full justify-between gap-2 text-left font-semibold">
      {writable ? "Busca CNPJá simulada" : "Busca externa · CNPJá"} <span aria-hidden="true">{open ? "−" : "+"}</span>
    </button>
    {open && <>
      {!writable && <p className="mt-2 text-sm text-muted">Até 10 empresas. A consulta pode consumir créditos quando o provedor estiver configurado.</p>}
      <form onSubmit={search} className="mt-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {fields.map(({ name, label, pattern }) => <label key={name} className="text-sm">
          {label}<input name={name} pattern={pattern} required inputMode={name === "uf" ? "text" : "numeric"}
            className={`mt-1 block w-full ${control}`} />
        </label>)}
        <button disabled={busy} className={`${primary} self-end`}>{loading ? "Consultando…" : "Buscar empresas"}</button>
      </form>
      {writable && <label className="mt-4 flex flex-wrap items-center gap-2 text-sm">
        Histórico de buscas
        <select aria-label="Histórico de buscas" className={control} disabled={busy} value={result?.id ?? ""}
          onChange={(event) => void loadHistory(event.target.value)}>
          <option value="">Escolher busca</option>
          {history.map((item) => <option key={item.id} value={item.id}>{item.tag}</option>)}
        </select>
      </label>}
      {feedback && <p role="status" className="mt-3 text-sm text-primary">{feedback}</p>}
      {result && (result.items.length ? <ul className="mt-3 max-h-72 divide-y divide-border overflow-y-auto">
        {result.items.map((company) => <li key={company.cnpj} className="flex items-center gap-3 py-2 text-sm">
          {writable && <input type="checkbox" aria-label={`Selecionar empresa ${company.razao_social}`} checked={selection.includes(company.cnpj)}
            onChange={(event) => setSelection((previous) => event.target.checked
              ? [...previous, company.cnpj] : previous.filter((id) => id !== company.cnpj))} />}
          <div><strong>{company.razao_social}</strong>
            <p className="text-muted">{company.cnpj} · {company.cidade}/{company.uf} · {company.data_abertura}</p></div>
        </li>)}
      </ul> : <p role="status" className="mt-3 text-sm text-muted">Nenhuma empresa encontrada.</p>)}
      {writable && result?.id && <button type="button" disabled={busy || !selection.length}
        onClick={() => void importSelected()} className={`${primary} mt-3`}>Importar selecionadas ({selection.length})</button>}
    </>}
  </Card>;
}
