"""Parse captured real DNS wire evidence and reject unbound/malformed answers."""

import base64
import json
import struct
from pathlib import Path

import pytest
from reputation_platform.infrastructure.network import operator_dns

SAVED = Path(__file__).resolve().parents[2] / "docs/testing/evidence/akashi-identity-2026-10-11/dns"


def test_real_operator_dns_answers_match_saved_addresses():
    for path in sorted(SAVED.glob("*.json")):
        evidence = json.loads(path.read_bytes())
        addresses = []
        for query in evidence["queries"]:
            wire = base64.b64decode(query["response_wire_base64"], validate=True)
            identifier = struct.unpack_from("!H", wire)[0]
            found, records = operator_dns.decode_answer(
                wire, identifier, query["query_type"], evidence["host"],
            )
            addresses.extend(found)
            assert records == query["records"]
        assert sorted(set(addresses)) == evidence["resolved_ips"]


@pytest.mark.parametrize("message", [b"", b"\xc0\x00", b"\x05abc", b"\xff"])
def test_dns_names_reject_truncation_and_pointer_loops(message):
    with pytest.raises((ValueError, UnicodeError)):
        operator_dns.dns_name(message, 0)


@pytest.mark.parametrize("mutation", ["identifier", "opcode", "question", "truncated", "trailing"])
def test_dns_answers_must_bind_to_the_original_query(mutation):
    evidence = json.loads(next(iter(sorted(SAVED.glob("*.json")))).read_bytes())
    query = evidence["queries"][0]
    wire = bytearray(base64.b64decode(query["response_wire_base64"], validate=True))
    identifier = struct.unpack_from("!H", wire)[0]
    host = evidence["host"]
    if mutation == "identifier":
        identifier ^= 1
    elif mutation == "opcode":
        wire[2] |= 0x08
    elif mutation == "question":
        host = "localhost"
    elif mutation == "truncated":
        wire = wire[:-1]
    else:
        wire += b"\0"
    with pytest.raises((ValueError, struct.error)):
        operator_dns.decode_answer(bytes(wire), identifier, query["query_type"], host)


def test_metadata_hosts_never_reach_operator_resolver(tmp_path, monkeypatch):
    def forbidden(*_, **__):
        pytest.fail("Unapproved host opened a DNS socket")
    monkeypatch.setattr(operator_dns.socket, "create_connection", forbidden)
    with pytest.raises(OSError, match="fixed Akashi and Base"):
        operator_dns.resolve_sync("metadata.example", tmp_path)
