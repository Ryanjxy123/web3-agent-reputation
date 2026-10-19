"""Pure verification of the supported CARv1 and UnixFS evidence format."""

import hashlib
import re


def _car_reader(car: bytes, root_digest: str):
    """Authenticate CAR blocks and expose the supported UnixFS reconstruction."""
    def varint(data: bytes, offset: int = 0) -> tuple[int, int]:
        value, shift = 0, 0
        while offset < len(data) and shift < 64:
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, offset
            shift += 7
        raise ValueError("Invalid or oversized varint")

    def cid(data: bytes, offset: int = 0) -> tuple[tuple[int, bytes], int]:
        version, offset = varint(data, offset)
        if version == 1:
            codec, offset = varint(data, offset)
            algorithm, offset = varint(data, offset)
        elif version == 18:
            codec, algorithm = 112, 18
        else:
            raise ValueError("Only CIDv0/v1 are supported")
        size, offset = varint(data, offset)
        if codec not in (112, 85) or algorithm != 18 or size != 32 or offset + size > len(data):
            raise ValueError("Only DAG-PB/raw with SHA2-256 is supported")
        return (codec, data[offset:offset + size]), offset + size

    def protobuf(data: bytes) -> dict[int, list]:
        fields, offset = {}, 0
        while offset < len(data):
            tag, offset = varint(data, offset)
            field, wire = tag >> 3, tag & 7
            if field == 0:
                raise ValueError("Invalid protobuf field")
            if wire == 0:
                value, offset = varint(data, offset)
            elif wire == 2:
                size, offset = varint(data, offset)
                if offset + size > len(data):
                    raise ValueError("Truncated protobuf value")
                value, offset = data[offset:offset + size], offset + size
            else:
                raise ValueError("Unsupported protobuf wire type")
            fields.setdefault(field, []).append(value)
        return fields

    header_size, offset = varint(car)
    header, offset = car[offset:offset + header_size], offset + header_size
    marker, suffix = b"\xa2eroots\x81\xd8\x2a\x58", b"\x67version\x01"
    if not header.startswith(marker) or len(header) <= len(marker):
        raise ValueError("Unsupported CAR header; expected canonical CARv1 with one root")
    root_size = header[len(marker)]
    root_bytes = header[len(marker) + 1:len(marker) + 1 + root_size]
    if (len(root_bytes) != root_size or not root_bytes.startswith(b"\x00")
        or header[len(marker) + 1 + root_size:] != suffix):
        raise ValueError("Invalid CAR root encoding")
    header_root, consumed = cid(root_bytes, 1)
    if consumed != len(root_bytes):
        raise ValueError("Trailing bytes in CAR root CID")
    blocks = {}
    while offset < len(car):
        size, offset = varint(car, offset)
        end = offset + size
        if size == 0 or end > len(car):
            raise ValueError("Truncated CAR block")
        identifier, payload_offset = cid(car, offset)
        if payload_offset > end:
            raise ValueError("CID extends beyond its CAR block")
        payload = car[payload_offset:end]
        if hashlib.sha256(payload).digest() != identifier[1]:
            raise ValueError("CAR block bytes do not match their CID")
        if identifier in blocks and blocks[identifier] != payload:
            raise ValueError("Conflicting duplicate CAR block")
        blocks[identifier], offset = payload, end

    def node(identifier: tuple[int, bytes]):
        if identifier[0] != 112 or identifier not in blocks:
            raise ValueError("A required DAG-PB block is missing")
        pb = protobuf(blocks[identifier])
        if len(pb.get(1, [])) != 1:
            raise ValueError("Expected one UnixFS data field")
        links = []
        for encoded in pb.get(2, []):
            link = protobuf(encoded)
            if len(link.get(1, [])) != 1 or len(link.get(2, [])) > 1:
                raise ValueError("Invalid DAG-PB link")
            child, consumed = cid(link[1][0])
            if consumed != len(link[1][0]):
                raise ValueError("Invalid link CID")
            links.append((link.get(2, [b""])[0].decode("utf-8"), child))
        return protobuf(pb[1][0]), links

    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", root_digest):
        raise ValueError("Expected a chain-anchored SHA256 digest")
    root = (112, bytes.fromhex(root_digest[2:]))
    root_data, links = node(root)

    def rebuild(identifier: tuple[int, bytes], depth: int = 0) -> bytes:
        if depth > 16 or identifier not in blocks:
            raise ValueError("Incomplete or excessive UnixFS traversal")
        if identifier[0] == 85:
            return blocks[identifier]
        unixfs, children = node(identifier)
        if unixfs.get(1) not in ([0], [2]) or len(unixfs.get(2, [])) > 1:
            raise ValueError("Expected a UnixFS raw/file node")
        sizes = unixfs.get(4, [])
        if len(sizes) != len(children):
            raise ValueError("UnixFS child sizes differ from the link count")
        pieces = [unixfs.get(2, [b""])[0]]
        total = len(pieces[0])
        if any(type(size) is not int or size < 0 for size in sizes) or total + sum(sizes) > 1_048_576:
            raise ValueError("UnixFS expansion exceeds the retained body limit")
        for (_, child), size in zip(children, sizes):
            piece = rebuild(child, depth + 1)
            if len(piece) != size:
                raise ValueError("UnixFS child size differs from reconstructed bytes")
            total += len(piece)
            pieces.append(piece)
        if unixfs.get(3) != [total]:
            raise ValueError("UnixFS file size differs from reconstructed bytes")
        return b"".join(pieces)

    return root, header_root, root_data, links, rebuild, len(blocks)


def inspect_car_root(car: bytes, root_digest: str) -> dict:
    """Identify the authenticated request root, without guessing a directory path."""
    _, _, unixfs, links, _, count = _car_reader(car, root_digest)
    if unixfs.get(1) == [1]:
        root_type = "directory"
    elif unixfs.get(1) in ([0], [2]):
        root_type = "file"
    else:
        raise ValueError("Unsupported UnixFS root type")
    return {"root_type": root_type, "root_digest": root_digest,
            "link_names": [name for name, _ in links], "car_blocks": count}


def read_car_file(car: bytes, root_digest: str, filename: str | None = None) -> tuple[bytes, dict]:
    """Extract a root file, or one explicit uniquely named directory member."""
    root, header_root, unixfs, links, rebuild, count = _car_reader(car, root_digest)
    if filename is None:
        if unixfs.get(1) not in ([0], [2]):
            raise ValueError("The chain-anchored root is not a UnixFS file")
        leaf = root
    else:
        if unixfs.get(1) != [1] or len([name for name, _ in links if name == filename]) != 1:
            raise ValueError("The chain-anchored UnixFS directory does not uniquely name the file")
        leaf = next(child for name, child in links if name == filename)
    if header_root not in (root, leaf):
        raise ValueError("CAR header root is unrelated to the requested path")
    actual = rebuild(leaf)
    return actual, {"verified": True, "root_digest": root_digest, "filename": filename,
                    "car_blocks": count, "file_bytes": len(actual), "file_sha256": hashlib.sha256(actual).hexdigest()}


def verify_car_file(car: bytes, root_digest: str, filename: str, expected_file: bytes) -> dict:
    """Preserve the original explicit-directory verification contract."""
    if filename is None:
        raise ValueError("Directory verification requires an explicit filename")
    actual, proof = read_car_file(car, root_digest, filename)
    if actual != expected_file:
        raise ValueError("Verified UnixFS file bytes differ from the retained JSON")
    return proof
