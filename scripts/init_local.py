"""Create a random local operator token without printing or overwriting secrets."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    path = ROOT / ".env"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    keys = {line.split("=", 1)[0] for line in existing.splitlines() if "=" in line}
    additions = []
    for name in ("OPERATOR_TOKEN", "POSTGRES_PASSWORD"):
        if name not in keys:
            additions.append(name + "=" + secrets.token_urlsafe(48))
    if "PUBLIC_ACCESS_ENABLED" not in keys:
        additions.append("PUBLIC_ACCESS_ENABLED=false")
    if additions:
        with path.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write("\n".join(additions) + "\n")
    print("Local .env prepared; existing credentials preserved, secrets never printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
