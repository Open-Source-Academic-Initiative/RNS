"""Funnel diagnostics: 60M..260M, 30 días, todos abiertos, perfil opensai.

Mide dónde se reduce el universo:
  A) Total Socrata con presupuesto + ventana + Abierto
  B) + guardas completas del repositorio (accionabilidad + seed)
  C) + IT_KEYWORD_PATTERN local
  D) - GENERIC_NEGATIVE_PATTERN local
  E) Después de perfil OpenSAI + dedupe + ranking (lo que llega a la UI)
"""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import timedelta
from typing import List

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
    params = [("%24select", "count(1) AS total"), ("%24where", where)]
    qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
    resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
    resp.raise_for_status()
    payload = resp.json()
    return int(payload[0].get("total") or 0) if payload else 0


async def fetch_records(client: httpx.AsyncClient, where: str, limit: int) -> List[dict]:
    params = [
        ("%24select", SECOP_SELECT_CLAUSE),
        ("%24where", where),
        ("%24limit", str(limit)),
        ("%24order", "fecha_de_publicacion_del DESC, precio_base DESC"),
    ]
    qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params)
    resp = await client.get(f"{BASE_URL}?{qs}", headers={"User-Agent": "RNS-diag/1"})
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, list) else []


async def main() -> None:
    repo = SocrataTenderRepository()
    now = repo._now()
    cutoff = (now - timedelta(days=30)).strftime(SODA_DATE_FORMAT)

    base_where = (
        f"precio_base >= 60000000 AND precio_base <= 260000000 "
        f"AND estado_de_apertura_del_proceso = 'Abierto' "
        f"AND fecha_de_publicacion_del >= '{cutoff}'"
    )
    repository_where = repo._build_where_clause(
        min_budget=60_000_000,
        max_budget=260_000_000,
        department="Todos",
        process_status="Todos",
        phase="Todos",
        published_since_days=30,
    )

    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        a_total = await fetch_count(client, base_where)
        b_total = await fetch_count(client, repository_where)
        records = await fetch_records(client, repository_where, limit=b_total + 50)

    print(f"Cutoff: {cutoff}, presupuesto 60M..260M, opening='Abierto'")
    print()
    print(f"A) base (precio + ventana + Abierto):     {a_total}")
    print(f"B) + guardas completas del repositorio:   {b_total}")
    print(f"   registros descargados realmente:       {len(records)}")

    after_kw = []
    after_neg = []
    dropped_kw = []
    dropped_neg = []
    for r in records:
        text = f"{r.get('nombre_del_procedimiento') or ''} {r.get('descripci_n_del_procedimiento') or ''}"
        if IT_KEYWORD_PATTERN.search(text):
            after_kw.append(r)
            if GENERIC_NEGATIVE_PATTERN.search(text):
                dropped_neg.append(r)
            else:
                after_neg.append(r)
        else:
            dropped_kw.append(r)

    print(f"C) + IT_KEYWORD_PATTERN local:            {len(after_kw)}")
    print(f"D) - exclusiones negativas locales:       {len(after_neg)}")

    results = repo.map_raw_records(after_neg, profile="opensai")
    print(f"E) tras perfil OpenSAI + dedupe:          {len(results)}")

    print()
    print("Ejemplos finales (lo que llega a la UI):")
    for tender in results[:10]:
        print(f"  + {int(tender.base_price):>14} | {tender.entity[:40]:40} | {tender.name[:90]}")

    print()
    print("Ejemplos descartados por keyword (entran al seed pero no al regex local):")
    for r in dropped_kw[:5]:
        print(f"  - {(r.get('nombre_del_procedimiento') or '')[:120]}")

    print()
    print("Top 10 entidades en E:")
    counts: dict[str, int] = {}
    for tender in results:
        counts[tender.entity or "?"] = counts.get(tender.entity or "?", 0) + 1
    for ent, n in sorted(counts.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {n:>3}  {ent}")

    await repo.aclose()


if __name__ == "__main__":
    asyncio.run(main())
