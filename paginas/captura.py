"""Captura de leads."""

from __future__ import annotations

from nucleo import ui

ui.cabecalho("Captura de leads", "Ponto de entrada único de leads.", secao="Prospecção")
ui.em_construcao(
    2,
    [
        "Formulário manual com busca de dados por CNPJ no CNPJ.ws, consentimento e base legal LGPD",
        "Importação de planilha CSV ou Excel com pré visualização dos problemas",
        "Lista de CNPJs conhecidos",
        "Formulário do site e webhook simulados, com chegada de leads em tempo real",
        "Carga da base fictícia de demonstração",
        "Envio para tratamento por lead ou por lote",
    ],
)
