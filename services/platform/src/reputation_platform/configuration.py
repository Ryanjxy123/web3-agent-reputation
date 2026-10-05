"""Validated process-local configuration for the controlled demo runtime."""

import os


def controlled_fixture_ports() -> tuple[int, int]:
    ports: list[int] = []
    for name, default in (("FIXTURE_PORT_A", 9101), ("FIXTURE_PORT_D", 9102)):
        raw = os.environ.get(name, str(default))
        try:
            port = int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc
        if not 1024 <= port <= 65535:
            raise ValueError(f"{name} must be between 1024 and 65535")
        ports.append(port)
    if ports[0] == ports[1]:
        raise ValueError("Controlled fixture ports must be distinct")
    return ports[0], ports[1]
