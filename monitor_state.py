"""Shared worker status storage in Supabase.

This table is separate from historico_sinais. It stores observation state only;
it never creates or modifies trading history.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from historico import obter_cliente


TABLE_NAME = "monitoramento_estado"


def salvar_estado_monitoramento(
    provider: str,
    ativo: str,
    status: str,
    sinal_candidato: str = "AGUARDAR",
    motivo: str = "",
    ultimo_dado: Optional[Any] = None,
    detalhes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if status not in {"observed", "error", "running"}:
        raise ValueError("Status de monitoramento inválido.")
    if sinal_candidato not in {"CALL", "PUT", "AGUARDAR"}:
        sinal_candidato = "AGUARDAR"

    agora = datetime.now(timezone.utc)
    payload = {
        "provider": str(provider).lower().strip(),
        "ativo": str(ativo).upper().strip(),
        "status": status,
        "sinal_candidato": sinal_candidato,
        "motivo": str(motivo)[:1000],
        "ultimo_ciclo": agora.isoformat(),
        "ultimo_dado": (
            ultimo_dado.isoformat()
            if hasattr(ultimo_dado, "isoformat")
            else (str(ultimo_dado) if ultimo_dado else None)
        ),
        "atualizado_em": agora.isoformat(),
        "detalhes": detalhes or {},
    }
    if not payload["provider"] or not payload["ativo"]:
        raise ValueError("provider e ativo são obrigatórios.")

    response = (
        obter_cliente()
        .table(TABLE_NAME)
        .upsert(payload, on_conflict="provider,ativo")
        .execute()
    )
    return (response.data or [payload])[0]


def listar_estado_monitoramento(limit: int = 20) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    response = (
        obter_cliente()
        .table(TABLE_NAME)
        .select(
            "provider,ativo,status,sinal_candidato,motivo,"
            "ultimo_ciclo,ultimo_dado,atualizado_em,detalhes"
        )
        .order("atualizado_em", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data or []
