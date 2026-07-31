"""Spike 5 - 8-K Item 4.02 candidate collection (re-run of design doc section 9-1).

Procedure (corrected acquisition method, section 8-2):
  1. FTS as HINT ONLY: forms=8-K, "Item 4.02" x 4 concept queries -> hint CIKs
  2. submissions API confirms: form == 8-K AND items contains 4.02 (authoritative)
  3. Filter: filing date >= 2019-01-01 (ASC 842 era)
  4. C4 industry-homonym exclusion by SIC

Output: docs/screener/data/spike5-8k-candidates.csv
Every row carries CIK + accession from the submissions API itself
(lineage contract clause 1: identity comes from the authoritative source, never FTS).
"""
import csv
import json
import time
from pathlib import Path

import requests

UA = {"User-Agent": "daria.j.kim@gmail.com spike5 research"}
FTS = "https://efts.sec.gov/LATEST/search-index"
OUT = Path("docs/screener/data/spike5-8k-candidates.csv")

# Section 9-1 concept queries (hint only)
QUERIES = [
    '"Item 4.02" "operating lease"',
    '"Item 4.02" "right-of-use"',
    '"Item 4.02" "intangible"',
    '"Item 4.02" "restatement"',
]

# C4 exclusion SICs (section 9-1 step 3)
C4_PREFIXES = ("13",)  # oil & gas 13xx
C4_EXACT = {"6798", "6500", "4911", "1382", "1000"}
C4_RANGES = [(6310, 6319), (6410, 6419)]


def sic_excluded(sic: str) -> bool:
    if not sic:
        return False
    if sic in C4_EXACT:
        return True
    if any(sic.startswith(p) for p in C4_PREFIXES):
        return True
    try:
        v = int(sic)
    except ValueError:
        return False
    return any(lo <= v <= hi for lo, hi in C4_RANGES)


def fts_hint_ciks() -> set[str]:
    ciks: set[str] = set()
    for q in QUERIES:
        frm = 0
        while True:
            r = requests.get(
                FTS,
                params={"q": q, "forms": "8-K", "from": frm},
                headers=UA, timeout=30,
            )
            if r.status_code != 200:
                print(f"FTS {q!r} from={frm}: HTTP {r.status_code}, stopping this query")
                break
            hits = r.json().get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                for c in h.get("_source", {}).get("ciks", []):
                    ciks.add(c.lstrip("0"))
            frm += len(hits)
            if frm >= 200:  # hint depth cap per query
                break
            time.sleep(0.15)
        time.sleep(0.15)
    return ciks


def confirm_via_submissions(cik: str) -> list[dict]:
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    r = requests.get(url, headers=UA, timeout=30)
    if r.status_code != 200:
        return [{"cik": cik, "error": f"HTTP {r.status_code}"}]
    j = r.json()
    name = j.get("name", "")
    sic = str(j.get("sic", "") or "")
    rows = []

    def scan(recent: dict):
        forms = recent.get("form", [])
        items = recent.get("items", [])
        dates = recent.get("filingDate", [])
        accs = recent.get("accessionNumber", [])
        docs = recent.get("primaryDocument", [])
        for i, f in enumerate(forms):
            if f in ("8-K", "8-K/A") and "4.02" in (items[i] or ""):
                rows.append({
                    "cik": cik, "company": name, "sic": sic,
                    "form": f, "filing_date": dates[i],
                    "accession": accs[i], "primary_doc": docs[i] if i < len(docs) else "",
                })

    scan(j.get("filings", {}).get("recent", {}))
    # older filings live in paged files
    for extra in j.get("filings", {}).get("files", []):
        r2 = requests.get(f"https://data.sec.gov/submissions/{extra['name']}", headers=UA, timeout=30)
        if r2.status_code == 200:
            scan(r2.json())
        time.sleep(0.11)
    return rows


def main():
    hints = fts_hint_ciks()
    print(f"FTS hint CIKs: {len(hints)}")
    all_rows, errors = [], []
    for n, cik in enumerate(sorted(hints, key=int)):
        for row in confirm_via_submissions(cik):
            (errors if "error" in row else all_rows).append(row)
        time.sleep(0.11)
        if (n + 1) % 25 == 0:
            print(f"  submissions checked: {n + 1}/{len(hints)}")
    print(f"confirmed Item 4.02 filings: {len(all_rows)} across "
          f"{len({r['cik'] for r in all_rows})} companies; lookup errors: {len(errors)}")

    recent = [r for r in all_rows if r["filing_date"] >= "2019-01-01"]
    print(f">=2019: {len(recent)} filings / {len({r['cik'] for r in recent})} companies")

    final = [r for r in recent if not sic_excluded(r["sic"])]
    excluded = [r for r in recent if sic_excluded(r["sic"])]
    print(f"after C4 SIC exclusion: {len(final)} filings "
          f"(excluded {len(excluded)}: {sorted({r['sic'] for r in excluded})})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cik", "company", "sic", "form",
                                          "filing_date", "accession", "primary_doc"])
        w.writeheader()
        w.writerows(sorted(final, key=lambda r: (r["filing_date"], r["cik"])))
    print(f"wrote {OUT}")
    if errors:
        print("ERRORS:", json.dumps(errors[:10], indent=2))


if __name__ == "__main__":
    main()
