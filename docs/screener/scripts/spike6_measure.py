"""Spike 6 - C' measurement per pre-registration (docs/screener/spike-6-*.md).

Pinned by the pre-registration (do not soften here):
  metric   = concept_value / Assets, same adsh, ddate = fiscal period end
  peers    = FSDS quarterly bulk (adsh-level, point-in-time), SIC4 n>=10 -> SIC3 -> no-verdict
  flag     = two-sided, outside [p5, p95] of the peer cell
  controls = >=100 randoms from the same cells, restatement-free (submissions items check)
  Y1 >= 8/15 measurable | Y2 sensitivity >= 40% | Y3 FPR <= 15% AND lift >= 2.5

Plumbing rules recorded (criteria unchanged):
  - For multi-year restatements, use the LATEST restated FY whose FSDS quarter is available.
  - Lease family: OperatingLeaseLiability total, else Current+Noncurrent sum.
  - Peer distribution = peers REPORTING the tag (a no-lease peer has no ratio).
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
CACHE = Path(r"C:\Users\user\AppData\Local\Temp\claude\C--Users-user-Desktop-crm-targeting-lab\85ddc3bf-c164-4c2f-a453-c24ec2baf649\scratchpad\fsds")
CACHE.mkdir(parents=True, exist_ok=True)
X2 = Path("docs/screener/data/spike5-x2-results.json")
OUT = Path("docs/screener/data/spike6-results.json")
random.seed(842350)  # ASC 842/350 - deterministic control sampling

FAMILY_TAGS = {
    "lease": (["OperatingLeaseLiability"], ["OperatingLeaseLiabilityCurrent", "OperatingLeaseLiabilityNoncurrent"]),
    "intangible": (["FiniteLivedIntangibleAssetsNet", "IntangibleAssetsNetExcludingGoodwill"], []),
    "goodwill": (["Goodwill"], []),
}
ALL_TAGS = sorted({t for m, s in FAMILY_TAGS.values() for t in m + s} | {"Assets"})


def quarter_of(date: str) -> str:
    y, m = int(date[:4]), int(date[5:7])
    return f"{y}q{(m - 1) // 3 + 1}"


def load_quarter(q: str):
    z = CACHE / f"{q}.zip"
    if not z.exists():
        url = f"https://www.sec.gov/files/dera/data/financial-statement-data-sets/{q}.zip"
        r = requests.get(url, headers=UA, timeout=300)
        if r.status_code != 200:
            return None
        z.write_bytes(r.content)
        time.sleep(0.2)
    zf = zipfile.ZipFile(z)
    sub = pd.read_csv(io.BytesIO(zf.read("sub.txt")), sep="\t", dtype=str,
                      usecols=["adsh", "cik", "name", "sic", "form", "period"])
    num = pd.read_csv(io.BytesIO(zf.read("num.txt")), sep="\t", dtype=str,
                      usecols=["adsh", "tag", "coreg", "ddate", "qtrs", "uom", "value"])
    num = num[num["tag"].isin(ALL_TAGS) & (num["qtrs"] == "0") & (num["uom"] == "USD")
              & (num["coreg"].isna() | (num["coreg"] == ""))]
    num["value"] = pd.to_numeric(num["value"], errors="coerce")
    return sub, num


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
    """Ratios for every 10-K peer in the SIC cell (peers reporting the tag)."""
    peers = sub[(sub["form"] == "10-K") & sub["sic"].notna()
                & sub["sic"].str.startswith(sic_prefix) & (sub["adsh"] != exclude_adsh)]
    ratios, rows = [], []
    for _, p in peers.iterrows():
        na = num[num["adsh"] == p["adsh"]]
        ddate = p["period"]
        cv, _ = concept_value(na, family, ddate)
        av = na[(na["tag"] == "Assets") & (na["ddate"] == ddate)]["value"].dropna()
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
        cand = [(y, v) for y, v in sorted(years.items(), reverse=True)]
        positives.append({"company": r["company"], "cik": r["cik"], "family": r["family"],
                          "candidates": cand})
    print(f"positives (misstatement track): {len(positives)}")

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
                rec.setdefault("notes", []).append(f"FY{fy}: value/Assets missing in num")
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
        print(p["company"], "->", rec.get("status"),
              "flag" if rec.get("flag") else "", flush=True)

    measured = [r for r in results if r["status"] == "measured"]
    flagged = [r for r in measured if r["flag"]]

    # ---- negative control: randoms from the SAME cells, restatement-free ----
    ctrl_results = []
    per_cell = max(1, -(-110 // max(1, len(controls_pool))))
    for (q, cell, family), rows in controls_pool.items():
        loaded = load_quarter(q)
        if loaded is None:
            continue
        sub, num = loaded
        pick = random.sample(rows, min(per_cell * 3, len(rows)))
        taken = 0
        for cand in pick:
            if taken >= per_cell or len(ctrl_results) >= 130:
                break
            if not is_restatement_free(cand["cik"]):
                continue
            prefix = cell.split()[1]
            ratios, _ = cell_ratios(sub, num, prefix, family, cand["adsh"])
            na = num[num["adsh"] == cand["adsh"]]
            row = sub[sub["adsh"] == cand["adsh"]].iloc[0]
            cv, _t = concept_value(na, family, row["period"])
            av = na[(na["tag"] == "Assets") & (na["ddate"] == row["period"])]["value"].dropna()
            if cv is None or not len(av) or len(ratios) < 10:
                continue
            fc = flag_in_cell(cv / float(av.iloc[0]), ratios)
            ctrl_results.append({"cik": cand["cik"], "name": cand["name"], "cell": cell,
                                 "quarter": q, "family": family, **fc})
            taken += 1
        print(f"controls {q}/{cell}: +{taken}", flush=True)

    n_ctrl = len(ctrl_results)
    fpr = sum(1 for c in ctrl_results if c["flag"]) / n_ctrl if n_ctrl else None
    sens = len(flagged) / len(measured) if measured else None
    out = {
        "preregistration": "spike-6-value-anomaly-preregistration.md (committed da6940b, before measurement)",
        "Y1": {"measurable": len(measured), "of": len(positives), "pass": len(measured) >= 8},
        "Y2": {"sensitivity": round(sens, 4) if sens is not None else None,
               "flagged": [r["company"] for r in flagged],
               "not_flagged": [r["company"] for r in measured if not r["flag"]],
               "pass": (sens is not None and sens >= 0.40)},
        "Y3": {"controls_n": n_ctrl, "false_positive_rate": round(fpr, 4) if fpr is not None else None,
               "lift": round(sens / fpr, 2) if (sens and fpr) else None,
               "pass": (fpr is not None and fpr <= 0.15 and sens and fpr and sens / fpr >= 2.5)},
        "positives_detail": results,
        "controls_detail": ctrl_results,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("Y1", "Y2", "Y3")}, indent=2))


if __name__ == "__main__":
    main()
