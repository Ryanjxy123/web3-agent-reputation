"""Append authenticated registration timing without changing a frozen history cohort."""

from datetime import datetime, timezone
import json
from pathlib import Path

from reputation_platform.prediction_evidence import PredictionProfile
from reputation_platform.prediction_report import (
    RetainedEvidence, _registration_timing, load_history_profile, verify_identity,
)

FIELDS = {'registration_evidence', 'registration_time', 'registration_block'}
SCHEMA = 'prediction-registration-supplement-v1'


def _directory(root: Path, run: Path) -> Path:
    path = (root / run).resolve()
    if (not path.is_relative_to(root / 'runtime') or path == root / 'runtime'
        or any(part.lower() in {'secrets', 'platform-config'} or '.private' in part.lower() for part in path.parts)):
        raise ValueError('Registration supplements require public runtime directories')
    return path


def _source(reader: RetainedEvidence, history: Path) -> tuple[dict, PredictionProfile, dict]:
    manifest = reader.manifest(history)
    name = (history / 'bundle.json').relative_to(reader.root).as_posix()
    bindings = [item for item in manifest['outputs'] if item['path'] == name]
    if len(bindings) != 1:
        raise ValueError('History bundle requires one authenticated manifest output')
    bundle_path = reader.remember(name, bindings[0]['sha256'])
    bundle = json.loads(bundle_path.read_bytes())
    profile = load_history_profile(reader, manifest, bundle)
    identity = verify_identity(reader, bundle, profile)
    manifest_name = (history / 'manifest.json').relative_to(reader.root).as_posix()
    references = {'bundle': {'path': name, 'sha256': reader.inputs[name]},
                  'manifest': {'path': manifest_name, 'sha256': reader.inputs[manifest_name]}}
    return bundle, profile, {'identity': identity, 'references': references}


def _check(reader: RetainedEvidence, history: Path, delta: dict) -> dict:
    if (set(delta) != FIELDS or not isinstance(delta['registration_evidence'], dict)
        or not {'transaction', 'receipt', 'header'} <= delta['registration_evidence'].keys()
        or type(delta['registration_block']) is not int or not isinstance(delta['registration_time'], str)):
        raise ValueError('A registration supplement must contain exactly the three supported timing fields')
    _, profile, source = _source(reader, history)
    checked = _registration_timing(reader.tree(delta), profile)
    snapshot = source['identity']['header']['value']
    if (checked['registration_block'] != delta['registration_block']
        or not 0 < checked['registration_block'] <= profile.snapshot_block
        or datetime.fromisoformat(checked['registration_time']).timestamp() > int(snapshot['timestamp'], 16)):
        raise ValueError('The authentic registration must match its stated block and precede the frozen snapshot')
    return source['references']


def write_registration_supplement(root: Path, run: Path, history_run: Path, identity: dict) -> Path:
    """Extract only mint evidence, date and block into a new append-only source run."""
    root = Path(root).resolve()
    run, history = _directory(root, Path(run)), _directory(root, Path(history_run))
    if run.is_relative_to(history):
        raise ValueError('A supplement cannot be written into its original history directory')
    if not FIELDS <= identity.keys():
        raise ValueError('Registration transaction evidence, date and block are required')
    delta = {name: identity[name] for name in sorted(FIELDS)}
    reader = RetainedEvidence(root)
    sources = _check(reader, history, delta)
    inputs = [{'path': name, 'sha256': digest} for name, digest in sorted(reader.inputs.items())]
    run.mkdir(parents=True, exist_ok=True)
    target = run / 'identity-supplement.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(delta, stream, ensure_ascii=False, indent=2)
    name = target.relative_to(root).as_posix()
    reader.remember(name)
    manifest = {'schema_version': SCHEMA, 'completed_at': datetime.now(timezone.utc).isoformat(),
        'source_history': sources, 'network_requests': 0, 'new_task_reads': 0,
        'inputs': inputs, 'outputs': [{'path': name, 'sha256': reader.inputs[name]}]}
    with (run / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return run


def validate_registration_supplement(root: Path, run: Path, history_run: Path) -> dict[str, str]:
    """Reauthenticate a timing-only supplement and return all source reference hashes."""
    root = Path(root).resolve()
    run, history = _directory(root, Path(run)), _directory(root, Path(history_run))
    if run.is_relative_to(history):
        raise ValueError('Registration supplements must be separate from the frozen history')
    reader = RetainedEvidence(root)
    manifest = reader.manifest(run)
    if manifest.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported registration supplement schema')
    name = (run / 'identity-supplement.json').relative_to(root).as_posix()
    outputs = manifest.get('outputs', [])
    if len(outputs) != 1 or outputs[0].get('path') != name:
        raise ValueError('A timing supplement requires exactly one bound identity-supplement output')
    delta = json.loads(reader.remember(name, outputs[0]['sha256']).read_bytes())
    sources = _check(reader, history, delta)
    if manifest.get('source_history') != sources:
        raise ValueError('Registration supplement belongs to a different frozen history source')
    inputs = {item['path']: item['sha256'] for item in manifest['inputs']}
    if len(inputs) != len(manifest['inputs']):
        raise ValueError('Registration supplement input references must be unique')
    local = {name, (run / 'manifest.json').relative_to(root).as_posix()}
    if any(inputs.get(path) != digest for path, digest in reader.inputs.items() if path not in local):
        raise ValueError('Registration supplement omitted an authenticated original source')
    return dict(reader.inputs)
