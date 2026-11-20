from __future__ import annotations

from dataclasses import dataclass, field

PORTES = ["MEI", "ME", "EPP", "Média", "Grande"]


@dataclass
class PerfilClienteIdeal:
    """Perfil do cliente ideal (ICP) usado para pontuar cada lead."""

    descricao: str
    setores: list[str] = field(default_factory=list)
    portes: list[str] = field(default_factory=list)
    ufs: list[str] = field(default_factory=list)
    cidades: list[str] = field(default_factory=list)

    def como_texto(self) -> str:
        partes = [f"Descrição: {self.descricao.strip() or '(não informada)'}"]
        partes.append(f"Setores-alvo: {', '.join(self.setores) or 'qualquer'}")
        partes.append(f"Portes-alvo: {', '.join(self.portes) or 'qualquer'}")
        local = [*self.cidades, *self.ufs]
        partes.append(f"Localização-alvo: {', '.join(local) or 'qualquer'}")
        return "\n".join(partes)

    def to_dict(self) -> dict:
        return {
            "descricao": self.descricao,
            "setores": self.setores,
            "portes": self.portes,
            "ufs": self.ufs,
            "cidades": self.cidades,
        }
