"""Spike 5 - X2 sensitivity measurement against ORIGINAL (pre-restatement) filings.

daria ruling (b), 2026-07-31: dual-track report.
  - absence-track (X2 denominator): omission/completeness positives only
  - misstatement-track: separate `misstatement_recall` label, NOT counted in X2

Method (point-in-time, NOT companyfacts - companyfacts merges amendments):
  For each qualified positive and each restated fiscal year, locate the ORIGINAL
  10-K (form == "10-K", filed BEFORE the 8-K date, reportDate in that FY),
  fetch its primary document (inline XBRL) plus any instance XML, and string-search
  for the standard tags. "Detected" = the pipeline's quarry condition holds:
  the standard liability/net tag is ABSENT from the original filing.

Output: docs/screener/data/spike5-x2-results.json
"""
import json
import time
from pathlib import Path

import requests

UA = {"User-Agent": "daria.j.kim@gmail.com spike5 research"}
ADJ = Path("docs/screener/data/spike5-adjudication.json")
OUT = Path("docs/screener/data/spike5-x2-results.json")

LEASE_LIAB = ["OperatingLeaseLiability"]  # substring covers Current/Noncurrent
LEASE_ROU = ["OperatingLeaseRightOfUseAsset"]
INTAN = ["FiniteLivedIntangibleAssetsNet", "IntangibleAssetsNetExcludingGoodwill"]
GOODWILL = ["Goodwill"]

# concept family per pass (from adjudication concepts)
FAMILY = {
    "Veroni Brands": "lease", "Tupperware Brands": "lease", "SS Innovations Intl": "lease",
    "Driven Brands": "lease", "Plug Power": "lease", "INVO Fertility": "lease",
    "Alpine 4 Holdings": "lease", "Adverum Biotechnologies": "lease",
    "Sonder Holdings": "lease", "FDCTech, Inc.": "lease", "American Rebel Holdings": "lease",
    "FuboTV Inc. (FaceBank)": "goodwill", "Odyssey Health, Inc.": "intangible",
    "Interpace Biosciences": "intangible", "Polished.com": "goodwill", "ADT Inc.": "goodwill",
    "Greenlane Holdings": "intangible", "LOGIQ, INC.": "intangible",
    "Healthcare Triangle": "intangible",
}


def fiscal_years(s: str) -> list[int]:
    import re
    ys = sorted({int(y) for y in re.findall(r"20\d\d", s)})
    if len(ys) == 2 and "-" in s:
        ys = list(range(ys[0], ys[1] + 1))
    return ys


def original_10ks(cik: str, before: str) -> list[dict]:
    r = requests.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json",
                     headers=UA, timeout=30)
    r.raise_for_status()
    j = r.json()
    res = []

    def scan(rec):
        for i, f in enumerate(rec.get("form", [])):
            if f == "10-K" and rec["filingDate"][i] < before:
                res.append({"accession": rec["accessionNumber"][i],
                            "filed": rec["filingDate"][i],
                            "report": rec.get("reportDate", [""] * 999)[i],
                            "primary": rec.get("primaryDocument", [""] * 999)[i]})

    scan(j.get("filings", {}).get("recent", {}))
    for extra in j.get("filings", {}).get("files", []):
        r2 = requests.get(f"https://data.sec.gov/submissions/{extra['name']}", headers=UA, timeout=30)
        if r2.status_code == 200:
            scan(r2.json())
        time.sleep(0.11)
    return res


def filing_text(cik: str, accession: str, primary: str) -> str:
    acc = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}"
    text = ""
    r = requests.get(f"{base}/{primary}", headers=UA, timeout=60)
    if r.status_code == 200:
        text += r.text
    # instance xml (pre-inline-XBRL era or exhibit instance)
    ri = requests.get(f"{base}/index.json", headers=UA, timeout=30)
    if ri.status_code == 200:
        for item in ri.json().get("directory", {}).get("item", []):
            n = item["name"].lower()
            if n.endswith(".xml") and not any(
                    s in n for s in ("_cal", "_def", "_lab", "_pre", ".xsd", "filingsummary")):
                r2 = requests.get(f"{base}/{item['name']}", headers=UA, timeout=60)
                if r2.status_code == 200:
                    text += r2.text
                time.sleep(0.11)
    return text


def main():
    adj = json.loads(ADJ.read_text(encoding="utf-8"))
    results = []
    for p in adj["passes"]:
        fam = FAMILY[p["company"]]
        tags_main = {"lease": LEASE_LIAB, "intangible": INTAN, "goodwill": GOODWILL}[fam]
        tags_aux = {"lease": LEASE_ROU, "intangible": GOODWILL, "goodwill": INTAN}[fam]
        rec = {"company": p["company"], "cik": p["cik"], "type": p["type"],
               "family": fam, "eight_k": p["filing_date"], "years": {}}
        try:
            tenks = original_10ks(p["cik"], p["filing_date"])
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)
            results.append(rec)
            continue
        for fy in fiscal_years(p["restated_annuals"]):
            cands = [t for t in tenks
                     if t["report"][:4] and fy <= int(t["report"][:4]) <= fy + 1
                     and (int(t["report"][:4]) == fy or int(t["report"][5:7]) <= 6)]
            if not cands:
                rec["years"][str(fy)] = {"status": "no_original_10k_found"}
                continue
            t = sorted(cands, key=lambda x: x["filed"])[0]
            try:
                text = filing_text(p["cik"], t["accession"], t["primary"])
            except Exception as e:  # noqa: BLE001
                rec["years"][str(fy)] = {"status": "fetch_error", "error": repr(e)}
                continue
            present_main = [tag for tag in tags_main if tag in text]
            present_aux = [tag for tag in tags_aux if tag in text]
            rec["years"][str(fy)] = {
                "status": "measured", "accession": t["accession"], "filed": t["filed"],
                "report": t["report"], "main_tags_present": present_main,
                "aux_tags_present": present_aux,
                "detected_as_residual": not present_main,
            }
            time.sleep(0.11)
        results.append(rec)
        print(f"{p['company']}: " + ", ".join(
            f"{y}={v.get('status')}/{'DETECTED' if v.get('detected_as_residual') else 'tag-present'}"
            for y, v in rec["years"].items()))

    absence = [r for r in results if r["type"] in ("omission", "omission?", "completeness")]
    miss = [r for r in results if r["type"] == "misstatement"]

    def company_detected(r):
        vals = [v for v in r["years"].values() if v.get("status") == "measured"]
        return any(v["detected_as_residual"] for v in vals) if vals else None

    out = {
        "ruling": "daria (b) 2026-07-31: dual-track",
        "absence_track": {
            "n": len(absence),
            "detected": [r["company"] for r in absence if company_detected(r)],
            "not_detected": [r["company"] for r in absence if company_detected(r) is False],
            "unmeasurable": [r["company"] for r in absence if company_detected(r) is None],
        },
        "misstatement_track_NOT_in_X2": {
            "n": len(miss),
            "misstatement_recall_hits": [r["company"] for r in miss if company_detected(r)],
            "tag_present_as_expected": [r["company"] for r in miss if company_detected(r) is False],
            "unmeasurable": [r["company"] for r in miss if company_detected(r) is None],
        },
        "detail": results,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    a = out["absence_track"]
    print(f"\nABSENCE TRACK: {len(a['detected'])}/{a['n']} detected "
          f"({a['unmeasurable']} unmeasurable)")
    m = out["misstatement_track_NOT_in_X2"]
    print(f"MISSTATEMENT TRACK (label only): {len(m['misstatement_recall_hits'])}/{m['n']} hits")


if __name__ == "__main__":
    main()
