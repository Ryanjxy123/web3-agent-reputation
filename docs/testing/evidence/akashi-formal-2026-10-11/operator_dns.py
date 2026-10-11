"""Untracked operator resolver: fixed Google DNS-over-TLS, never metadata supplied."""

import asyncio
import base64
import hashlib
import ipaddress
import json
import secrets
import socket
import struct
from datetime import UTC, datetime
from pathlib import Path

import httpx

HOST = "anchor.akashi-notari.com"
RESOLVER_IP = "8.8.8.8"
TLS_NAME = "dns.google"
EVIDENCE = Path.cwd() / "runtime/task8-trusted-dns-reproduction"


def read_exact(stream, size):
    output = bytearray()
    while len(output) < size:
        chunk = stream.recv(size - len(output))
        if not chunk:
            raise OSError("DNS-over-TLS EOF")
        output.extend(chunk)
    return bytes(output)


def dns_name(message, offset):
    labels, visited, resume = [], set(), None
    while True:
        if offset >= len(message) or offset in visited:
            raise ValueError("Invalid DNS name")
        visited.add(offset)
        length = message[offset]
        offset += 1
        if length == 0:
            return ".".join(labels).lower(), resume or offset
        if length & 0xC0 == 0xC0:
            if offset >= len(message):
                raise ValueError("Truncated DNS pointer")
            pointer = ((length & 0x3F) << 8) | message[offset]
            resume = resume or offset + 1
            offset = pointer
        elif length & 0xC0 or offset + length > len(message):
            raise ValueError("Invalid DNS label")
        else:
            labels.append(message[offset:offset + length].decode("ascii"))
            offset += length
            if len(labels) > 127:
                raise ValueError("Too many DNS labels")


def decode_answer(message, identifier, query_type):
    response_id, flags, questions, answers, authorities, additional = struct.unpack("!6H", message[:12])
    if response_id != identifier or flags & 0x8000 == 0 or flags & 0x0200 or flags & 0x000F or questions != 1:
        raise ValueError("Rejected DNS header")
    question, offset = dns_name(message, 12)
    actual_type, query_class = struct.unpack_from("!HH", message, offset)
    if (question, actual_type, query_class) != (HOST, query_type, 1):
        raise ValueError("DNS question mismatch")
    offset += 4
    records = []
    for index in range(answers + authorities + additional):
        owner, offset = dns_name(message, offset)
        kind, record_class, ttl, size = struct.unpack_from("!HHIH", message, offset)
        offset += 10
        data_end = offset + size
        if data_end > len(message):
            raise ValueError("Truncated DNS record")
        if index < answers and record_class == 1:
            if kind == 5:
                target, consumed = dns_name(message, offset)
                if consumed != data_end:
                    raise ValueError("Invalid DNS CNAME")
                records.append({"owner": owner, "type": kind, "ttl": ttl, "target": target})
            elif kind in (1, 28):
                if size != (4 if kind == 1 else 16):
                    raise ValueError("Invalid DNS address length")
                records.append({"owner": owner, "type": kind, "ttl": ttl,
                                "address": str(ipaddress.ip_address(message[offset:data_end]))})
        offset = data_end
    if offset != len(message):
        raise ValueError("DNS trailing bytes")
    names = {HOST}
    for _ in range(answers):
        names.update(record["target"] for record in records if record["type"] == 5 and record["owner"] in names)
    addresses = [record["address"] for record in records if record["type"] == query_type and record["owner"] in names]
    return addresses, records


def resolve_sync(host):
    if host != HOST:
        raise OSError("Trusted resolver only accepts Akashi")
    observations, addresses = [], []
    context = httpx.create_ssl_context(trust_env=False)
    with socket.create_connection((RESOLVER_IP, 853), timeout=8) as connection:
        with context.wrap_socket(connection, server_hostname=TLS_NAME) as stream:
            cert_hash = hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest()
            for kind in (1, 28):
                identifier = secrets.randbits(16)
                question = b"".join(bytes([len(label)]) + label.encode("ascii") for label in host.split(".")) + b"\0"
                wire = struct.pack("!6H", identifier, 0x0100, 1, 0, 0, 0) + question + struct.pack("!HH", kind, 1)
                stream.sendall(struct.pack("!H", len(wire)) + wire)
                size = struct.unpack("!H", read_exact(stream, 2))[0]
                if size < 12:
                    raise OSError("Truncated DNS response")
                response = read_exact(stream, size)
                try:
                    found, records = decode_answer(response, identifier, kind)
                except (ValueError, UnicodeError, struct.error):
                    raise OSError("Trusted DNS response rejected") from None
                addresses.extend(found)
                observations.append({"query_type": kind, "query_wire_base64": base64.b64encode(wire).decode(),
                                     "response_wire_base64": base64.b64encode(response).decode(), "records": records})
            observed_at = datetime.now(UTC).isoformat()
            evidence = {"host": host, "source": "fixed-operator-dns-over-tls", "resolver_ip": RESOLVER_IP,
                        "resolver_port": 853, "tls_server_name": TLS_NAME, "tls_verified": True,
                        "tls_version": stream.version(), "certificate_sha256": cert_hash,
                        "dnssec_verified": False, "observed_at": observed_at,
                        "queries": observations, "resolved_ips": sorted(set(addresses))}
    if not addresses:
        raise OSError("No public DNS addresses")
    EVIDENCE.mkdir(exist_ok=True)
    destination = EVIDENCE / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ") + ".json")
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sorted(set(addresses))


async def resolve(host):
    return await asyncio.to_thread(resolve_sync, host)


if __name__ == "__main__":
    for malformed in (b"", b"\xc0\x00", b"\x05abc", b"\xff"):
        try:
            dns_name(malformed, 0)
        except (ValueError, UnicodeError):
            pass
        else:
            raise AssertionError("Malformed DNS name accepted")
    print(json.dumps({"host": HOST, "resolved_ips": asyncio.run(resolve(HOST)), "evidence_dir": str(EVIDENCE)}))
