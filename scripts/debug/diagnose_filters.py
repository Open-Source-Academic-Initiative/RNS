"""Diagnose por qué la UI no muestra oportunidades con los filtros del usuario.

Reproduce los filtros del formulario:
  min=0, max=10_000_000_000, ventana=7 días, departamento=Todos,
  estado=Todos abiertos, etapa=Todas, perfil=opensai, sin keyword.

Mide cuántos registros caen en cada etapa del pipeline:
  A) Solo presupuesto + ventana + opening_status='Abierto'
  B) + cláusula seed (LIKE OR-chain en Socrata)
  C) + IT_KEYWORD_PATTERN local
  D) - GENERIC_NEGATIVE_PATTERN local
  E) Después de dedupe + ranking (lo que llega a la UI)
"""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import timedelta
from typing import Any, List

import httpx

from src.infrastructure.constants import (
    GENERIC_NEGATIVE_PATTERN,
    IT_KEYWORD_PATTERN,
    SOCRATA_LIKE_SEEDS,
)
from src.infrastructure.repositories import (
    DEFAULT_TIMEZONE,
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


def build_seed_clause() -> str:
    fragments = []
    for seed in SOCRATA_LIKE_SEEDS:
        safe = seed.replace("'", "''").upper()
        fragments.append(f"UPPER(nombre_del_procedimiento) LIKE '%{safe}%'")
        fragments.append(f"UPPER(descripci_n_del_procedimiento) LIKE '%{safe}%'")
    return "(" + " OR ".join(fragments) + ")"


async def main() -> None:
    repo = SocrataTenderRepository()
    now = repo._now()
    cutoff = (now - timedelta(days=7)).strftime(SODA_DATE_FORMAT)

    base_where = (
        f"precio_base >= 0 AND precio_base <= 10000000000 "
        f"AND estado_de_apertura_del_proceso = 'Abierto' "
        f"AND fecha_de_publicacion_del >= '{cutoff}'"
    )
    seed_clause = build_seed_clause()
    seeded_where = f"{base_where} AND {seed_clause}"

    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        a_total = await fetch_count(client, base_where)
        b_total = await fetch_count(client, seeded_where)
        records = await fetch_records(client, seeded_where, limit=2000)

    print(f"Hora local Bogotá: {now.isoformat()}")
    print(f"Cutoff publicación: {cutoff}")
    print(f"Seed clause len: {len(seed_clause)}")
    print()
    print(f"A) precio + ventana + opening='Abierto': {a_total}")
    print(f"B) + seed LIKE OR-chain Socrata:        {b_total}")

    after_kw = 0
    after_neg = 0
    samples_kept: list[str] = []
    samples_dropped_kw: list[str] = []
    samples_dropped_neg: list[str] = []
    for r in records:
        text = f"{r.get('nombre_del_procedimiento') or ''} {r.get('descripci_n_del_procedimiento') or ''}"
        if IT_KEYWORD_PATTERN.search(text):
            after_kw += 1
            if GENERIC_NEGATIVE_PATTERN.search(text):
                if len(samples_dropped_neg) < 3:
                    samples_dropped_neg.append(r.get("nombre_del_procedimiento") or "")
                continue
            after_neg += 1
            if len(samples_kept) < 5:
                samples_kept.append(r.get("nombre_del_procedimiento") or "")
        else:
            if len(samples_dropped_kw) < 3:
                samples_dropped_kw.append(r.get("nombre_del_procedimiento") or "")

    print(f"C) + IT_KEYWORD_PATTERN local (de B):   {after_kw}")
    print(f"D) - negative exclusions local:          {after_neg}")
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
