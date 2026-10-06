"""Command-line verification: python -m eval.evaluate
Writes eval/report.md and eval/report.json."""
import json
from pathlib import Path

from app.evaluation import run_evaluation, write_report

if __name__ == "__main__":
    out = Path(__file__).parent
    result = run_evaluation()
    write_report(result, out / "report.md")
    (out / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for name, m in result["sets"].items():
        print(f"== {name}: {m['description']}")
        for k, v in m.items():
            if k != "description":
                print(f"   {k:28} {v}")
    if result["misclassified"]:
        print("misclassified:", result["misclassified"])
    print(f"Report written to {out / 'report.md'}")
