"""One ASGI route check; repository doubles do not claim PostgreSQL integration."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.parse import quote

from fastapi.testclient import TestClient

from reputation_core.application import AgentDetail, AgentSummary
from reputation_platform.api import create_app


class AgentKeyRouteTests(unittest.TestCase):
    def test_slash_and_legacy_keys_keep_detail_chain_and_attachment_routes(self):
        keys = ('mcp-registry:fi.ophis/mcp@0.2.0', 'hydrex-routing-54947')
        agents = {key: AgentDetail(agent=AgentSummary(key=key, name=key,
            registration_reference=key, description='Controlled route case', report_count=0,
            latest_report=None), reports=[], candidate=None) for key in keys}
        with tempfile.TemporaryDirectory(prefix='agent-key-routes-') as directory:
            evidence = Path(directory) / 'public-evidence.bin'
            evidence.write_bytes(b'Controlled public attachment')
            repository = Mock()
            repository.get_agent.side_effect = agents.get
            repository.list_agents.return_value = [item.agent for item in agents.values()]
            repository.agent_chain_evidence.return_value = None
            repository.agent_chain_evidence_file.side_effect = (
                lambda key, path: evidence if key in agents and path == 'runtime/public-evidence.bin' else None)
            with TestClient(create_app(repository)) as client:
                response = client.get('/api/agents')
                self.assertEqual(response.status_code, 200)
                self.assertEqual({item['key'] for item in response.json()}, set(keys))
                for key in keys:
                    with self.subTest(key=key):
                        base = '/api/agents/' + quote(key, safe='')
                        response = client.get(base)
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json()['agent']['key'], key)
                        repository.get_agent.assert_called_with(key)
                        response = client.get(base + '/chain-evidence')
                        self.assertEqual(response.status_code, 200)
                        self.assertIsNone(response.json())
                        repository.agent_chain_evidence.assert_called_with(key)
                        response = client.get(base + '/chain-evidence/file',
                                              params={'path': 'runtime/public-evidence.bin'})
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.content, evidence.read_bytes())
                        repository.agent_chain_evidence_file.assert_called_with(key, 'runtime/public-evidence.bin')
                        self.assertEqual(client.get(base + '/chain-evidence/file',
                            params={'path': 'runtime/unreferenced.bin'}).status_code, 404)
                unknown = '/api/agents/' + quote('mcp-registry:example/unknown@0.1.0', safe='')
                self.assertEqual(client.get(unknown).status_code, 404)
                self.assertEqual(client.get(unknown + '/chain-evidence').status_code, 404)
                self.assertEqual(client.get(unknown + '/chain-evidence/file',
                    params={'path': 'runtime/public-evidence.bin'}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
