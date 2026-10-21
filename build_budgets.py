"""Write the site's budgets.js from data/budgets.csv.

    python build_budgets.py

Each club gets its tier and how sure it is: "official" (a league publication), "press" (a figure reported in the
press) or "estimate" (no published figure; tier estimated). Notes stay in the CSV; only the figure, season and source
go to the site.
"""
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
SITE = Path(r"C:\Users\antonis\Desktop\nikolitso.github.io\fibaeuropecup")


def main():
    clubs = []
    for r in csv.DictReader(open(ROOT / "data" / "budgets.csv", encoding="utf-8")):
        if r["tier_basis"] != "published figure":
            status = "estimate"
        elif r["kind"].startswith("official"):
            status = "official"
        else:
            status = "press"
        clubs.append({"club": r["club"], "tier": r["tier"], "status": status,
                      "budget": float(r["budget_m"]) if r["budget_m"] and status != "estimate" else None,
                      "currency": r["currency"], "season": r["season"] if status != "estimate" else "",
                      "source": r["source"] if status != "estimate" else ""})
    out = {"updated": date.today().isoformat(), "clubs": clubs}
    text = ("// Club budget tiers for this season's FIBA Europe Cup, built by build_budgets.py from data/budgets.csv.\n"
            "window.BUDGETS = " + json.dumps(out, ensure_ascii=False) + ";\n")
    (ROOT / "data" / "budgets.js").write_text(text, encoding="utf-8")   # private only: the site no longer shows budgets
    print(f"budgets.js: {len(clubs)} clubs")


if __name__ == "__main__":
    main()
