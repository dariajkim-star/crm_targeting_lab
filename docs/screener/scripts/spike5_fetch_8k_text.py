"""Spike 5 - fetch each candidate 8-K and extract the Item 4.02 narrative.

Output: docs/screener/data/spike5-8k-snippets.jsonl
One JSON object per filing: identity (cik, accession) + extracted snippet.
Rows where the primary document cannot be fetched are recorded with an error
field rather than dropped (absence gets a name).
"""
import csv
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path

import requests

UA = {"User-Agent": "daria.j.kim@gmail.com spike5 research"}
SRC = Path("docs/screener/data/spike5-8k-candidates.csv")
OUT = Path("docs/screener/data/spike5-8k-snippets.jsonl")


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, d):
        if not self.skip:
            self.parts.append(d)


def to_text(html: str) -> str:
    p = Text()
    p.feed(html)
    t = " ".join(p.parts)
    return re.sub(r"\s+", " ", t)


def extract_402(text: str) -> str:
    m = re.search(r"item\s*4\.?02", text, re.I)
    if not m:
        return text[:5000]
    start = max(0, m.start() - 200)
    return text[start:m.start() + 6000]


def main():
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    out = OUT.open("w", encoding="utf-8")
    ok = err = 0
    for i, r in enumerate(rows):
        acc = r["accession"].replace("-", "")
        rec = dict(r)
        url = f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{acc}/{r['primary_doc']}"
        try:
            resp = requests.get(url, headers=UA, timeout=30)
            if resp.status_code != 200:
                # fall back to the filing index text file
                url2 = f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{acc}.txt"
                resp = requests.get(url2, headers=UA, timeout=30)
            if resp.status_code == 200:
                rec["snippet"] = extract_402(to_text(resp.text))
                ok += 1
            else:
                rec["error"] = f"HTTP {resp.status_code}"
                err += 1
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)
            err += 1
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        time.sleep(0.11)
        if (i + 1) % 25 == 0:
            print(f"fetched {i + 1}/{len(rows)} (ok {ok}, err {err})")
    out.close()
    print(f"done: ok {ok}, err {err} -> {OUT}")


if __name__ == "__main__":
    main()
