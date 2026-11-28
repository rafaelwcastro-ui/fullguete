"use client";

import { useState, type FormEvent } from "react";
import { Card } from "@/components/ui/card";

type Company = {
  cnpj: string;
  razao_social: string;
  cidade: string;
  uf: string;
  cnae: string;
  data_abertura: string;
};

const fields = [
  { name: "uf", label: "UF", pattern: "[A-Za-z]{2}" },
  { name: "municipio_ibge", label: "Código IBGE do município", pattern: "[0-9]{7}" },
  { name: "cnae", label: "CNAE", pattern: "[0-9]{7}" },
  { name: "mes", label: "Mês de abertura", pattern: "(0?[1-9]|1[0-2])" },
  { name: "ano", label: "Ano de abertura", pattern: "(20[0-9]{2}|2100)" },
];

export function CompanySearch({ onExpired }: { onExpired: () => void }) {
  const [items, setItems] = useState<Company[] | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setItems(null);
    setError("");
    setPending(true);
    try {
      const result = await fetch("/api/operacao/company-search", {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          uf: String(form.get("uf")).toUpperCase(),
          municipio_ibge: Number(form.get("municipio_ibge")),
          ano: Number(form.get("ano")),
          mes: Number(form.get("mes")),
          cnae: String(form.get("cnae")),
        }),
      });
      if (result.status === 401) {
        onExpired();
        return;
      }
      const body = await result.json();
      if (!result.ok) throw new Error(body.detail);
      setItems(body.items);
    } catch (failure) {
      setError(failure instanceof Error && failure.message ? failure.message : "A consulta está indisponível.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Card>
      <h2 className="font-semibold">Busca externa · CNPJá</h2>
      <p className="mt-2 text-sm text-muted">Até 10 empresas. Quando o provedor estiver configurado, a consulta poderá consumir créditos. A busca não importa registros.</p>
      <form onSubmit={search} className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map(({ name, label, pattern }) => (
          <label key={name} className="text-sm">
            {label}
            <input name={name} pattern={pattern} required inputMode={name === "uf" ? "text" : "numeric"}
              className="mt-1 block w-full rounded-lg border border-border bg-background p-2" />
          </label>
        ))}
        <button disabled={pending} className="nav-active self-end rounded-lg p-2 font-semibold disabled:opacity-50">
          {pending ? "Consultando..." : "Consultar CNPJá"}
        </button>
      </form>
      {error && <p role="alert" className="mt-4 text-sm text-[#f5ce91]">{error}</p>}
      {items && <p role="status" className="mt-4 text-sm text-muted">{items.length ? `${items.length} empresa(s)` : "Nenhuma empresa encontrada."}</p>}
      {!!items?.length && <ul className="mt-2 divide-y divide-border">
        {items.map((company, index) => (
          <li key={`${company.cnpj}-${index}`} className="py-3 text-sm">
            <strong>{company.razao_social}</strong>
            <p className="mt-1 text-muted">{company.cnpj} · {company.cidade}/{company.uf} · CNAE {company.cnae} · {company.data_abertura || "Abertura não informada"}</p>
          </li>
        ))}
      </ul>}
    </Card>
  );
}
