"""Diagnose por qué la UI no muestra oportunidades con los filtros del usuario.

Reproduce los filtros del formulario:
  min=0, max=10_000_000_000, ventana=7 días, departamento=Todos,
  estado=Todos abiertos, etapa=Todas, perfil=opensai, sin keyword.

Mide cuántos registros caen en cada etapa del pipeline:
  A) Solo presupuesto + ventana + opening_status='Abierto'
  B) + guardas completas del repositorio (accionabilidad + seed)
  C) + IT_KEYWORD_PATTERN local
  D) - GENERIC_NEGATIVE_PATTERN local
  E) Después de perfil OpenSAI + dedupe + ranking (lo que llega a la UI)
"""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import timedelta
from typing import Any, List

import httpx

import _bootstrap  # noqa: F401

from src.infrastructure.constants import (
    GENERIC_NEGATIVE_PATTERN,
    IT_KEYWORD_PATTERN,
)
from src.infrastructure.repositories import (
    SECOP_SELECT_CLAUSE,
    SODA_DATE_FORMAT,
    SocrataTenderRepository,
)


BASE_URL = SocrataTenderRepository.BASE_URL


async def fetch_count(client: httpx.AsyncClient, where: str) -> int:
    params = [
        ("%24select", "count(1) AS total"),
        ("%24where", where),
    ]
    qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
    resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
    resp.raise_for_status()
    payload = resp.json()
    if not payload:
        return 0
    return int(payload[0].get("total") or 0)


async def fetch_records(client: httpx.AsyncClient, where: str, limit: int = 1000) -> List[dict]:
    params = [
        ("%24select", SECOP_SELECT_CLAUSE),
        ("%24where", where),
        ("%24limit", str(limit)),
        ("%24order", "fecha_de_publicacion_del DESC"),
    ]
    qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
    resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, list) else []


async def main() -> None:
    repo = SocrataTenderRepository()
    now = repo._now()
    cutoff = (now - timedelta(days=7)).strftime(SODA_DATE_FORMAT)

    base_where = (
        f"precio_base >= 0 AND precio_base <= 10000000000 "
        f"AND estado_de_apertura_del_proceso = 'Abierto' "
        f"AND fecha_de_publicacion_del >= '{cutoff}'"
    )
    repository_where = repo._build_where_clause(
        min_budget=0,
        max_budget=10_000_000_000,
        department="Todos",
        process_status="Todos",
        phase="Todos",
        published_since_days=7,
    )

    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        a_total = await fetch_count(client, base_where)
        b_total = await fetch_count(client, repository_where)
        records = await fetch_records(client, repository_where, limit=2000)

    print(f"Hora local Bogotá: {now.isoformat()}")
    print(f"Cutoff publicación: {cutoff}")
    print(f"Repository where len: {len(repository_where)}")
    print()
    print(f"A) precio + ventana + opening='Abierto': {a_total}")
    print(f"B) + guardas completas del repositorio: {b_total}")

    after_kw: list[dict[str, Any]] = []
    after_neg: list[dict[str, Any]] = []
    samples_kept: list[str] = []
    samples_dropped_kw: list[str] = []
    samples_dropped_neg: list[str] = []
    for r in records:
        text = f"{r.get('nombre_del_procedimiento') or ''} {r.get('descripci_n_del_procedimiento') or ''}"
        if IT_KEYWORD_PATTERN.search(text):
            after_kw.append(r)
            if GENERIC_NEGATIVE_PATTERN.search(text):
                if len(samples_dropped_neg) < 3:
                    samples_dropped_neg.append(r.get("nombre_del_procedimiento") or "")
                continue
            after_neg.append(r)
            if len(samples_kept) < 5:
                samples_kept.append(r.get("nombre_del_procedimiento") or "")
        else:
            if len(samples_dropped_kw) < 3:
                samples_dropped_kw.append(r.get("nombre_del_procedimiento") or "")

    results = repo.map_raw_records(after_neg, profile="opensai")

    print(f"C) + IT_KEYWORD_PATTERN local (de B):   {len(after_kw)}")
    print(f"D) - negative exclusions local:          {len(after_neg)}")
    print(f"E) tras perfil OpenSAI + dedupe:         {len(results)}")
    print()
    print("Ejemplos que pasan todo el pipeline:")
    for s in samples_kept:
        print(f"  + {s[:120]}")
    print()
    print("Ejemplos que entran en B pero NO matchea IT_KEYWORD_PATTERN local:")
    for s in samples_dropped_kw:
        print(f"  - {s[:120]}")
    print()
    print("Ejemplos descartados por exclusiones negativas:")
    for s in samples_dropped_neg:
        print(f"  ! {s[:120]}")

    await repo.aclose()


if __name__ == "__main__":
    asyncio.run(main())
