from __future__ import annotations

import argparse
import json
from pathlib import Path


def generate_dataset(size: int) -> list[dict[str, str]]:
    return [
        {
            "url": f"https://fixture.example/page-{index}",
            "html": (
                "<html><head>"
                f"<title>Fixture page {index}</title>"
                f"<meta name='description' content='Synthetic fixture {index}'>"
                "</head><body>"
                f"<a href='/page-{(index + 1) % size}'>Next</a>"
                "</body></html>"
            ),
        }
        for index in range(size)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic AtlasPipe fixture data.")
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("tests/fixtures/generated_pages.json"))
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(generate_dataset(args.size), indent=2), encoding="utf-8")
    print(f"wrote {args.size} fixture records to {args.output}")


if __name__ == "__main__":
    main()
