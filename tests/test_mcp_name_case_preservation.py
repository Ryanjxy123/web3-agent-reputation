"""One offline actual-registry acceptance: case preservation without case-insensitive identity."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote

from reputation_core.application import normalize_reference
from reputation_platform.public_service_identity import verify_service_identity


class McpNameCasePreservation(unittest.TestCase):
    def test_real_official_case_and_strict_case_url_metadata_remote_binding(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/mcp_name_case_preservation_case.json').read_bytes())
        canonical, proof_name = fixture['canonical'], fixture['proof_path']
        self.assertEqual(normalize_reference(canonical), canonical)
        wrong_case = canonical.lower()
        self.assertNotEqual(wrong_case, canonical)
        self.assertEqual(normalize_reference(wrong_case), wrong_case)
        with tempfile.TemporaryDirectory(prefix='mcp-case-offline-') as directory:
            root = Path(directory)
            for row in fixture['files']:
                raw = base64.b64decode(row['base64'], validate=True)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
                self.assertNotIn('.private', row['path'])
                path = root / row['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            proof_path = root / proof_name
            original = proof_path.read_bytes()
            proof = json.loads(original)
            observation_path = root / proof['registry_observation']
            original_observation = observation_path.read_bytes()
            observation = json.loads(original_observation)
            body_path = observation_path.parent / observation['response_file']
            original_body = body_path.read_bytes()
            result = verify_service_identity(root, proof_name, canonical)
            self.assertEqual(result['canonical'], canonical)
            self.assertTrue(result['public_registry_verified'])
            self.assertFalse(result['chain_registration_verified'])
            self.assertFalse(result['registration_verified'])
            self.assertIsNone(result['registration_chain_id'])
            self.assertIn(proof['selected_service'], [s['endpoint'] for s in result['document']['services']])
            self.assertEqual(result['background_findings'][0]['verdict'], 'UNKNOWN')
            with self.assertRaisesRegex(ValueError, 'identity/schema'):
                verify_service_identity(root, proof_name, wrong_case)

            def changed(*, reference=canonical, url=None, body=None, endpoint=None):
                candidate = deepcopy(proof)
                candidate['canonical'] = reference
                if endpoint is not None:
                    candidate['selected_service'] = endpoint
                obs = deepcopy(observation)
                if url is not None:
                    obs['url'] = url
                body_path.write_bytes(original_body if body is None else json.dumps(body).encode())
                obs['response_sha256'] = hashlib.sha256(body_path.read_bytes()).hexdigest()
                observation_path.write_text(json.dumps(obs), encoding='utf-8')
                for ref in candidate['source_refs']:
                    ref['sha256'] = hashlib.sha256((root / ref['path']).read_bytes()).hexdigest()
                proof_path.write_text(json.dumps(candidate), encoding='utf-8')

            # Local proof and URL are coherently casefolded and hashes repaired;
            # the untouched real official server.name still rejects that identity.
            name, version = wrong_case[len('mcp-registry:'):].rsplit('@', 1)
            url = 'https://registry.modelcontextprotocol.io/v0.1/servers/' + quote(name, safe='') + '/versions/' + version
            changed(reference=wrong_case, url=url)
            with self.assertRaisesRegex(ValueError, 'name/version'):
                verify_service_identity(root, proof_name, wrong_case)
            tampered = json.loads(original_body)
            tampered['server']['name'] = tampered['server']['name'].lower()
            changed(body=tampered)
            with self.assertRaisesRegex(ValueError, 'name/version'):
                verify_service_identity(root, proof_name, canonical)
            changed(url=url)
            with self.assertRaisesRegex(ValueError, 'official HTTPS GET'):
                verify_service_identity(root, proof_name, canonical)
            changed(endpoint='https://unrelated.example/mcp')
            with self.assertRaisesRegex(ValueError, 'remote'):
                verify_service_identity(root, proof_name, canonical)
            proof_path.write_bytes(original)
            observation_path.write_bytes(original_observation)
            body_path.write_bytes(original_body)
            self.assertTrue(verify_service_identity(root, proof_name, canonical)['public_registry_verified'])

        for invalid in ('mcp-registry:io.github.TSаvo/swapchan@0.3.0',  # Cyrillic a
                        'mcp-registry:io.github.K/swapchan@0.3.0',
                        'mcp-registry:io.github.TSavo/swapchan@latest',
                        'mcp-registry:io.github.TSavo//swapchan@0.3.0',
                        'MCP-registry:io.github.TSavo/swapchan@0.3.0'):
            self.assertIsNone(normalize_reference(invalid))
        self.assertEqual(normalize_reference('mcp-registry:fi.ophis/mcp@0.2.0'), 'mcp-registry:fi.ophis/mcp@0.2.0')
        self.assertEqual(normalize_reference('eip155:08453:0x' + 'AB' * 20 + ':00042'),
                         'eip155:8453:0x' + 'ab' * 20 + ':42')
        self.assertEqual(normalize_reference('acp:virtuals:019EB95D-2E16-7EA6-80FD-384434761336'),
                         'acp:virtuals:019eb95d-2e16-7ea6-80fd-384434761336')


if __name__ == '__main__':
    unittest.main()
