"""Verify live API, web proxy and Anvil without disclosing credentials."""

import json
import time
import urllib.error
import urllib.request


def main() -> None:
    deadline = time.monotonic() + 120
    urls = ["http://127.0.0.1:8000/health/ready", "http://127.0.0.1:5173/health/ready"]
    for url in urls:
        while True:
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    body = json.load(response)
                assert body["database"] == "ready"
                break
            except (OSError, ValueError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Runtime health did not become ready") from None
                time.sleep(2)
    request = urllib.request.Request(
        "http://127.0.0.1:8545",
        json.dumps({"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.load(response)["result"] == "0x7a69"
    request = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/agents", b"{}", {"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("Unauthenticated mutation was accepted")
    print("LIVE_RUNTIME_PASS: API, web proxy, auth and local Anvil")


if __name__ == "__main__":
    main()
