"""Funnel diagnostics: 60M..260M, 30 días, todos abiertos, perfil opensai.

Mide dónde se reduce el universo:
  A) Total Socrata con presupuesto + ventana + Abierto
  B) + cláusula seed (LIKE OR-chain)
  C) + IT_KEYWORD_PATTERN local
  D) - GENERIC_NEGATIVE_PATTERN local
  E) Después de dedupe por cluster_id (lo que llega a la UI)
"""

from __future__ import annotations

import asyncio
import urllib.parse
from datetime import timedelta
from typing import List

import httpx

from src.infrastructure.constants import (
    GENERIC_NEGATIVE_PATTERN,
    IT_KEYWORD_PATTERN,
    SOCRATA_LIKE_SEEDS,
)
from src.infrastructure.repositories import (
    SECOP_SELECT_CLAUSE,
    SODA_DATE_FORMAT,
    SocrataTenderRepository,
)


BASE_URL = SocrataTenderRepository.BASE_URL


def build_seed_clause() -> str:
    fragments = []
    for seed in SOCRATA_LIKE_SEEDS:
        safe = seed.replace("'", "''").upper()
        fragments.append(f"UPPER(nombre_del_procedimiento) LIKE '%{safe}%'")
        fragments.append(f"UPPER(descripci_n_del_procedimiento) LIKE '%{safe}%'")
    return "(" + " OR ".join(fragments) + ")"


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
    seed_clause = build_seed_clause()
    seeded_where = f"{base_where} AND {seed_clause}"

    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        a_total = await fetch_count(client, base_where)
        b_total = await fetch_count(client, seeded_where)
        records = await fetch_records(client, seeded_where, limit=b_total + 50)

    print(f"Cutoff: {cutoff}, presupuesto 60M..260M, opening='Abierto'")
    print()
    print(f"A) base (precio + ventana + Abierto):     {a_total}")
    print(f"B) + seed LIKE OR-chain Socrata:          {b_total}")
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

    # Dedup by cluster_id signature
    seen = {}
    for r in after_neg:
        entity = (r.get("entidad") or "").lower()
        name = (r.get("nombre_del_procedimiento") or "").lower()[:180]
        price = str(int(float(r.get("precio_base") or 0)))
        key = f"{entity}|{name}|{price}"
        seen.setdefault(key, r)
    print(f"E) tras dedupe por cluster_id:            {len(seen)}")

    print()
    print("Ejemplos finales (lo que llega a la UI):")
    for r in list(seen.values())[:10]:
        print(f"  + {r.get('precio_base'):>14} | {r.get('entidad')[:40]:40} | {(r.get('nombre_del_procedimiento') or '')[:90]}")

    print()
    print("Ejemplos descartados por keyword (entran al seed pero no al regex local):")
    for r in dropped_kw[:5]:
        print(f"  - {(r.get('nombre_del_procedimiento') or '')[:120]}")

    print()
    print("Top 10 entidades en E:")
    counts: dict[str, int] = {}
    for r in seen.values():
        counts[r.get("entidad") or "?"] = counts.get(r.get("entidad") or "?", 0) + 1
    for ent, n in sorted(counts.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {n:>3}  {ent}")

    await repo.aclose()


if __name__ == "__main__":
    asyncio.run(main())
