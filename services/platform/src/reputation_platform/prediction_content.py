"""Collect explicitly authenticated UnixFS root files or declared directory members."""

import json
import re
import secrets

from reputation_core.ipfs import inspect_car_root, read_car_file, verify_car_file


def collect_root_or_path_content(store, name: str, digest: str, filename: str) -> dict:
    """Read one root CAR first; directories retain their original explicit file path."""
    # Local import permits the existing store to opt into this helper without a cycle.
    from reputation_platform.prediction_evidence import GATEWAY, file_reference

    if (not re.fullmatch(r'[a-z0-9-]+', name) or not re.fullmatch(r'0x[0-9a-f]{64}', digest)
        or not re.fullmatch(r'metadata\.json|[0-9]+', filename)):
        raise ValueError('Unsupported fixed request CID, content key or declared filename')
    url = GATEWAY + 'f01701220' + digest[2:] + '?format=car&dag-scope=entity'
    car = store.request(name + '-root-car', url)
    root = inspect_car_root(car['raw'], digest)
    if root['root_type'] == 'directory':
        if root['link_names'].count(filename) != 1:
            raise ValueError('Authenticated directory does not uniquely name the declared file')
        path_url = GATEWAY + 'f01701220' + digest[2:] + '/' + filename
        content = store.request(name, path_url)
        path_car = store.request(name + '-car', path_url + '?format=car&dag-scope=entity')
        raw = content['raw']
        proof = verify_car_file(path_car['raw'], digest, filename, raw)
        fields = {'layout': 'unixfs-directory-v1', 'url': path_url,
            'response_file': content['response_file'], 'car_file': path_car['response_file'],
            'root_car_file': car['response_file'], 'evidence': car['evidence'] + content['evidence'] + path_car['evidence']}
    else:
        raw, proof = read_car_file(car['raw'], digest)
        derived = store.run / (name + '-root-file-' + secrets.token_hex(8) + '.json')
        with derived.open('xb') as stream:
            stream.write(raw)
        derived_ref = file_reference(derived, store.root)
        store._remember([derived_ref])
        fields = {'layout': 'unixfs-root-file-v1', 'url': url,
            'response_file': derived_ref['path'], 'car_file': car['response_file'],
            'evidence': car['evidence'] + [derived_ref]}
    format_error = None
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            payload, format_error = None, 'CID-authenticated content is not the declared JSON object'
    except (ValueError, UnicodeError):
        payload, format_error = None, 'CID-authenticated bytes are not valid JSON'
    return {**fields, 'payload': payload, 'sha256': proof['file_sha256'],
            'car_verification': proof, 'format_error': format_error}
