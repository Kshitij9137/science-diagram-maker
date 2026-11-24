"""Generate diagrams and save them to data/results.json.

  python -m scripts.generate_all                 # all concepts that are missing or failed
  python -m scripts.generate_all --only 3        # just concept 3 (if missing/failed)
  python -m scripts.generate_all --only 3 --force  # regenerate 3 even if it passed
  python -m scripts.generate_all --force         # regenerate everything
"""
import argparse
import json
import logging
import os
import time

from app import config
from app.concepts import CONCEPTS
from app.services.orchestrator import GenerationError, generate_diagram


def load_results():
    """Existing results as {concept_id: result}. Empty if the file doesn't exist yet."""
    if config.RESULTS_FILE.exists():
        data = json.loads(config.RESULTS_FILE.read_text(encoding="utf-8"))
        return {item["concept_id"]: item for item in data}
    return {}


def save_results(by_id):
    """Write results in concept order. Writes to a temp file first, then swaps it in,
    so a crash mid-write can't leave a half-written results.json."""
    config.RESULTS_FILE.parent.mkdir(exist_ok=True)
    ordered = [by_id[cid] for cid in CONCEPTS if cid in by_id]
    temp = config.RESULTS_FILE.with_suffix(".json.tmp")
    # ensure_ascii=False keeps symbols like ² and ₂ readable in the file
    temp.write_text(json.dumps(ordered, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, config.RESULTS_FILE)


def main():
    parser = argparse.ArgumentParser(description="Generate science diagrams")
    parser.add_argument("--only", nargs="+", metavar="ID", help="concept ids, e.g. --only 2 4")
    parser.add_argument("--force", action="store_true", help="regenerate even if already passed")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    targets = args.only or list(CONCEPTS)
    unknown = [cid for cid in targets if cid not in CONCEPTS]
    if unknown:
        raise SystemExit(f"Unknown concept id(s): {unknown}. Valid ids: {list(CONCEPTS)}")

    results = load_results()
    errors = {}
    generated_any = False

    for cid in targets:
        existing = results.get(cid)
        if existing and existing["status"] == "passed" and not args.force:
            print(f"[{cid}] {CONCEPTS[cid]['name']}: already passed, skipping (use --force)")
            continue

        if generated_any:
            time.sleep(config.DELAY_BETWEEN_CONCEPTS)  # be gentle with the free tier
        generated_any = True

        try:
            results[cid] = generate_diagram(cid, profile="batch")
            save_results(results)   # save immediately
        except GenerationError as error:
            errors[cid] = error.message
            print(f"[{cid}] FAILED, keeping the old result if there is one: {error.message}")

    # ---- summary
    print("\n=== Summary ===")
    for cid in CONCEPTS:
        item = results.get(cid)
        if item:
            print(f"{cid}. {item['concept_name']:<22} {item['status']:<7} "
                  f"${item['cost_usd']:<10} retries={item['retries']['total']}")
        else:
            print(f"{cid}. {CONCEPTS[cid]['name']:<22} MISSING  {errors.get(cid, '')}")
    if len(results) < len(CONCEPTS):
        print("\nSome concepts are missing. Wait a minute, then run the script again.")


if __name__ == "__main__":
    main()