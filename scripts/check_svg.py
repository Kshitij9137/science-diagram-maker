import sys

from app import config
from app.services.svg_validator import validate_svg


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else str(config.BASE_DIR / "test_output.svg")
    svg = open(path, encoding="utf-8").read()
    checks = validate_svg(svg)
    print(f"File: {path}\n")
    for name, result in checks.items():
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"[{mark}] {name}: {result['reason']}")


if __name__ == "__main__":
    main()