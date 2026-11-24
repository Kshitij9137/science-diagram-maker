import logging
import sys

from app import config
from app.services.orchestrator import GenerationError, generate_diagram


def main():
    concept_id = sys.argv[1] if len(sys.argv) > 1 else "1"
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        result = generate_diagram(concept_id)
    except GenerationError as error:
        print(f"\nGeneration failed: {error.message}")
        return

    out_file = config.BASE_DIR / f"test_output_{concept_id}.svg"
    out_file.write_text(result["svg"], encoding="utf-8")

    print(f"\n=== {result['concept_name']} ===")
    print(f"Status:  {result['status']}   Model: {result['model']}")
    print(f"Tokens:  {result['tokens']}")
    print(f"Cost:    ${result['cost_usd']}  (estimate)")
    print(f"Retries: {result['retries']}")
    for name, check in result["checks"].items():
        print(f"  [{'PASS' if check['passed'] else 'FAIL'}] {name}: {check['reason']}")
    print(f"\nSVG saved to {out_file}")


if __name__ == "__main__":
    main()