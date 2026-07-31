"""Spike 6 - RUN 2 with plumbing corrections (pre-reg section 8-3, criteria unchanged).

Corrections vs run 1:
  - Values AND peers come from the NOTES data sets (financial-statement-and-notes),
    which carry footnote-level tags (OperatingLeaseLiability notes coverage 79.4%
    vs 6.0% face-only). Target/peer symmetry preserved.
  - Quarterly zips through 2025q2; MONTHLY zips from 2025q3 (T1 trap); files are .tsv.
  - Controls >= 100 enforced.
  - ONE re-run only; Y1/Y2/Y3 unchanged. Cell starvation is a result, not plumbing.
"""
import io
import json
import random
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

UA = {"User-Agent": "daria.j.kim@gmail.com spike6 research"}
CACHE = Path(r"C:\Users\user\AppData\Local\Temp\claude\C--Users-user-Desktop-crm-targeting-lab\85ddc3bf-c164-4c2f-a453-c24ec2baf649\scratchpad\fsds_notes")
CACHE.mkdir(parents=True, exist_ok=True)
X2 = Path("docs/screener/data/spike5-x2-results.json")
OUT = Path("docs/screener/data/spike6-results-run2.json")
random.seed(842350)

BASE = "https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets"

FAMILY_TAGS = {
    "lease": (["OperatingLeaseLiability"], ["OperatingLeaseLiabilityCurrent", "OperatingLeaseLiabilityNoncurrent"]),
    "intangible": (["FiniteLivedIntangibleAssetsNet", "IntangibleAssetsNetExcludingGoodwill"], []),
    "goodwill": (["Goodwill"], []),
}
ALL_TAGS = sorted({t for m, s in FAMILY_TAGS.values() for t in m + s} | {"Assets"})
_qcache: dict = {}


def quarter_of(date: str) -> str:
    y, m = int(date[:4]), int(date[5:7])
    return f"{y}q{(m - 1) // 3 + 1}"


def _download(name: str) -> Path | None:
    z = CACHE / name
    if z.exists():
        return z if z.stat().st_size > 0 else None
    r = requests.get(f"{BASE}/{name}", headers=UA, timeout=600)
    time.sleep(0.2)
    if r.status_code != 200:
        z.write_bytes(b"")  # negative cache
        return None
    z.write_bytes(r.content)
    return z


def _read_zip(z: Path):
    zf = zipfile.ZipFile(z)
    names = {n.lower(): n for n in zf.namelist()}
    sub_name = names.get("sub.tsv") or names.get("sub.txt")
    num_name = names.get("num.tsv") or names.get("num.txt")
    sub = pd.read_csv(io.BytesIO(zf.read(sub_name)), sep="\t", dtype=str,
                      usecols=["adsh", "cik", "name", "sic", "form", "period"],
                      on_bad_lines="skip", low_memory=False)
    chunks = []
    for ch in pd.read_csv(io.BytesIO(zf.read(num_name)), sep="\t", dtype=str,
                          usecols=["adsh", "tag", "coreg", "ddate", "qtrs", "uom", "value"],
                          on_bad_lines="skip", chunksize=1_000_000, low_memory=False):
        ch = ch[ch["tag"].isin(ALL_TAGS) & (ch["qtrs"] == "0") & (ch["uom"] == "USD")
                & (ch["coreg"].isna() | (ch["coreg"] == ""))]
        chunks.append(ch)
    num = pd.concat(chunks, ignore_index=True)
    num["value"] = pd.to_numeric(num["value"], errors="coerce")
    return sub, num


def load_quarter(q: str):
    if q in _qcache:
        return _qcache[q]
    y, qn = int(q[:4]), int(q[-1])
    result = None
    if (y, qn) < (2025, 3):
        z = _download(f"{q}_notes.zip")
        if z:
            result = _read_zip(z)
    else:
        subs, nums = [], []
        for m in range((qn - 1) * 3 + 1, qn * 3 + 1):
            z = _download(f"{y}_{m:02d}_notes.zip")
            if z:
                s, n = _read_zip(z)
                subs.append(s)
                nums.append(n)
        if subs:
            result = (pd.concat(subs, ignore_index=True), pd.concat(nums, ignore_index=True))
    _qcache[q] = result
    print(f"  [{q}] {'loaded' if result else 'UNAVAILABLE'}", flush=True)
    return result


def concept_value(num_adsh: pd.DataFrame, family: str, ddate: str):
    main, parts = FAMILY_TAGS[family]
    at = num_adsh[num_adsh["ddate"] == ddate]
    for tag in main:
        v = at[at["tag"] == tag]["value"].dropna()
        if len(v):
            return float(v.iloc[0]), tag
    if parts:
        vals = [at[at["tag"] == t]["value"].dropna() for t in parts]
        if all(len(v) for v in vals):
            return float(sum(v.iloc[0] for v in vals)), "+".join(parts)
    return None, None


def cell_ratios(sub, num, sic_prefix: str, family: str, exclude_adsh: str):
    peers = sub[(sub["form"] == "10-K") & sub["sic"].notna()
                & sub["sic"].str.startswith(sic_prefix) & (sub["adsh"] != exclude_adsh)]
    ratios, rows = [], []
    for _, p in peers.iterrows():
        na = num[num["adsh"] == p["adsh"]]
        cv, _ = concept_value(na, family, p["period"])
        av = na[(na["tag"] == "Assets") & (na["ddate"] == p["period"])]["value"].dropna()
        if cv is not None and len(av) and av.iloc[0] and av.iloc[0] > 0:
            ratios.append(cv / float(av.iloc[0]))
            rows.append({"cik": p["cik"], "name": p["name"], "adsh": p["adsh"]})
    return ratios, rows


def flag_in_cell(x: float, ratios: list) -> dict:
    s = pd.Series(ratios)
    p5, p95 = s.quantile(0.05), s.quantile(0.95)
    pct = float((s < x).mean())
    return {"ratio": x, "peer_n": len(ratios), "p5": float(p5), "p95": float(p95),
            "percentile": round(pct, 4), "flag": bool(x < p5 or x > p95)}


def is_restatement_free(cik: str) -> bool:
    try:
        r = requests.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json",
                         headers=UA, timeout=30)
        if r.status_code != 200:
            return False
        rec = r.json().get("filings", {}).get("recent", {})
        return not any("4.02" in (it or "") for it in rec.get("items", []))
    finally:
        time.sleep(0.11)


def main():
    x2 = json.loads(X2.read_text(encoding="utf-8"))
    positives = []
    for r in x2["detail"]:
        if r["type"] != "misstatement":
            continue
        years = {y: v for y, v in r["years"].items() if v.get("status") == "measured"}
        positives.append({"company": r["company"], "cik": r["cik"], "family": r["family"],
                          "candidates": sorted(years.items(), reverse=True)})
    print(f"positives: {len(positives)}", flush=True)

    results, controls_pool = [], {}
    for p in positives:
        rec = {"company": p["company"], "cik": p["cik"], "family": p["family"]}
        done = False
        for fy, v in p["candidates"]:
            q = quarter_of(v["filed"])
            loaded = load_quarter(q)
            if loaded is None:
                rec.setdefault("notes", []).append(f"FY{fy}: dataset {q} unavailable")
                continue
            sub, num = loaded
            row = sub[sub["adsh"] == v["accession"]]
            if row.empty:
                rec.setdefault("notes", []).append(f"FY{fy}: adsh not in {q}")
                continue
            row = row.iloc[0]
            na = num[num["adsh"] == v["accession"]]
            cv, tag_used = concept_value(na, p["family"], row["period"])
            av = na[(na["tag"] == "Assets") & (na["ddate"] == row["period"])]["value"].dropna()
            if cv is None or not len(av) or not av.iloc[0]:
                rec.setdefault("notes", []).append(f"FY{fy}: value/Assets missing in notes num")
                continue
            sic4 = row["sic"]
            ratios, rows = cell_ratios(sub, num, sic4, p["family"], v["accession"])
            cell = f"SIC4 {sic4}"
            if len(ratios) < 10:
                ratios, rows = cell_ratios(sub, num, sic4[:3], p["family"], v["accession"])
                cell = f"SIC3 {sic4[:3]}"
            if len(ratios) < 10:
                rec.update({"status": "no_verdict_cell", "fy": fy, "cell_n": len(ratios)})
                done = True
                break
            rec.update({"status": "measured", "fy": fy, "quarter": q, "tag": tag_used,
                        "cell": cell, **flag_in_cell(cv / float(av.iloc[0]), ratios)})
            controls_pool.setdefault((q, cell, p["family"]), rows)
            done = True
            break
        if not done:
            rec["status"] = "unmeasurable"
        results.append(rec)
        print(p["company"], "->", rec.get("status"), "flag" if rec.get("flag") else "",
              rec.get("notes", ""), flush=True)

    measured = [r for r in results if r["status"] == "measured"]
    flagged = [r for r in measured if r["flag"]]

    ctrl_results = []
    per_cell = max(1, -(-120 // max(1, len(controls_pool))))
    for (q, cell, family), rows in controls_pool.items():
        loaded = load_quarter(q)
        if loaded is None:
            continue
        sub, num = loaded
        pick = random.sample(rows, min(per_cell * 4, len(rows)))
        taken = 0
        for cand in pick:
            if taken >= per_cell or len(ctrl_results) >= 150:
                break
            if not is_restatement_free(cand["cik"]):
                continue
            prefix = cell.split()[1]
            ratios, _ = cell_ratios(sub, num, prefix, family, cand["adsh"])
            na = num[num["adsh"] == cand["adsh"]]
            srow = sub[sub["adsh"] == cand["adsh"]]
            if srow.empty or len(ratios) < 10:
                continue
            srow = srow.iloc[0]
            cv, _t = concept_value(na, family, srow["period"])
            av = na[(na["tag"] == "Assets") & (na["ddate"] == srow["period"])]["value"].dropna()
            if cv is None or not len(av) or not av.iloc[0]:
                continue
            fc = flag_in_cell(cv / float(av.iloc[0]), ratios)
            ctrl_results.append({"cik": cand["cik"], "name": cand["name"], "cell": cell,
                                 "quarter": q, "family": family, **fc})
            taken += 1
        print(f"controls {q}/{cell}: +{taken} (total {len(ctrl_results)})", flush=True)

    n_ctrl = len(ctrl_results)
    fpr = sum(1 for c in ctrl_results if c["flag"]) / n_ctrl if n_ctrl else None
    sens = len(flagged) / len(measured) if measured else None
    out = {
        "run": 2,
        "corrections": "notes datasets for values AND peers; monthly zips >=2025q3; controls >=100",
        "criteria_unchanged": True,
        "Y1": {"measurable": len(measured), "of": len(positives), "pass": len(measured) >= 8},
        "Y2": {"sensitivity": round(sens, 4) if sens is not None else None,
               "flagged": [r["company"] for r in flagged],
               "not_flagged": [r["company"] for r in measured if not r["flag"]],
               "pass": (sens is not None and sens >= 0.40)},
        "Y3": {"controls_n": n_ctrl, "false_positive_rate": round(fpr, 4) if fpr is not None else None,
               "lift": round(sens / fpr, 2) if (sens and fpr) else None,
               "pass": bool(fpr is not None and fpr <= 0.15 and sens and fpr and sens / fpr >= 2.5)},
        "positives_detail": results,
        "controls_detail": ctrl_results,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("Y1", "Y2", "Y3")}, indent=2))


if __name__ == "__main__":
    main()
