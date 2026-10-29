"""One offline acceptance over real retained public registry and provider event bytes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from reputation_core.application import normalize_reference
from reputation_platform.public_service_identity import verify_service_identity, verify_public_service_identity
from reputation_platform.registration_discovery import _identity


class PublicServiceIdentityAcceptance(unittest.TestCase):
    def test_real_public_registry_binding_and_tampering_without_fabricated_chain_identity(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/public_service_identity_case.json').read_bytes())
        with tempfile.TemporaryDirectory(prefix='public-service-identity-') as temporary:
            root=Path(temporary)
            for row in fixture['files']:
                path=root/row['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(row['raw_utf8'].encode())
            mcp,acp=fixture['proof_paths']
            canonical_mcp='mcp-registry:fi.ophis/mcp@0.2.0'
            canonical_acp='acp:virtuals:019eb95d-2e16-7ea6-80fd-384434761336'
            for name,canonical in ((mcp,canonical_mcp),(acp,canonical_acp)):
                self.assertEqual(normalize_reference(canonical),canonical)
                result=verify_service_identity(root,name,canonical)
                self.assertTrue(result['public_registry_verified'])
                self.assertFalse(result['chain_registration_verified'])
                self.assertFalse(result['registration_verified'])
                self.assertIsNone(result['registration_chain_id'])
                self.assertEqual(result['background_findings'][0]['verdict'],'UNKNOWN')
            actual=verify_public_service_identity(root,acp,canonical_acp)
            self.assertTrue(actual['provider_chain_event_verified'])
            self.assertEqual(actual['provider_wallet'],'0xe4bce29bc099e2a04369f6a2df98dc7d5eac2ac7')
            self.assertIn('https://mcp.ophis.fi/mcp',[x['endpoint'] for x in verify_public_service_identity(root,mcp,canonical_mcp)['document']['services']])

            original=(root/mcp).read_bytes();proof=json.loads(original)
            forged=dict(proof,selected_service='https://unrelated.example/mcp')
            (root/mcp).write_text(json.dumps(forged),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'remote'):
                verify_public_service_identity(root,mcp,canonical_mcp)
            (root/mcp).write_bytes(original)
            claimed=dict(proof,registration_verified=True,chain_registration_verified=True)
            (root/mcp).write_text(json.dumps(claimed),encoding='utf8')
            self.assertFalse(verify_public_service_identity(root,mcp,canonical_mcp)['chain_registration_verified'])
            (root/mcp).write_bytes(original)

            # Repairing local hashes cannot make a different official version,
            # latest search endpoint or offering match the selected identity.
            def mutate_observation(proof_path,observation_path,change_body=None,change_observation=None):
                p=json.loads((root/proof_path).read_bytes());obs=json.loads((root/observation_path).read_bytes())
                response=(Path(observation_path).parent/obs['response_file']).as_posix()
                if change_body:
                    body=json.loads((root/response).read_bytes());change_body(body)
                    (root/response).write_text(json.dumps(body),encoding='utf8')
                    obs['response_sha256']=hashlib.sha256((root/response).read_bytes()).hexdigest()
                if change_observation:change_observation(obs)
                (root/observation_path).write_text(json.dumps(obs),encoding='utf8')
                for row in p['source_refs']:
                    row['sha256']=hashlib.sha256((root/row['path']).read_bytes()).hexdigest()
                (root/proof_path).write_text(json.dumps(p),encoding='utf8')
            mcp_obs=proof['registry_observation']
            mutate_observation(mcp,mcp_obs,change_body=lambda body:body['server'].update(version='0.2.1'))
            with self.assertRaisesRegex(ValueError,'name/version'):
                verify_public_service_identity(root,mcp,canonical_mcp)

            acp_original=(root/acp).read_bytes();ap=json.loads(acp_original)
            (root/acp).write_text(json.dumps(dict(ap,offering='batch_screen')),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'offering'):
                verify_public_service_identity(root,acp,canonical_acp)
            (root/acp).write_bytes(acp_original)
            no_event=copy.deepcopy(ap);no_event.pop('provider_event')
            (root/acp).write_text(json.dumps(no_event),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'real Base provider event'):
                verify_public_service_identity(root,acp,canonical_acp)
            (root/acp).write_bytes(acp_original)
            missing_chain=copy.deepcopy(ap)
            chain_names=[]
            for name in ap['provider_event']['rpc_observations']:
                observation=json.loads((root/name).read_bytes())
                if json.loads(observation['request_json'])['method']=='eth_chainId':chain_names.append(name)
            self.assertTrue(chain_names)
            missing_chain['provider_event']['rpc_observations']=[name for name in missing_chain['provider_event']['rpc_observations'] if name not in chain_names]
            (root/acp).write_text(json.dumps(missing_chain),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'successful eth_chainId'):
                verify_public_service_identity(root,acp,canonical_acp)
            (root/acp).write_bytes(acp_original)
            mutate_observation(acp,chain_names[0],change_body=lambda body:body.update(result='0x38'))
            with self.assertRaisesRegex(ValueError,'successful eth_chainId'):
                verify_public_service_identity(root,acp,canonical_acp)
            # Restore retained originals before the independent provider-topic control.
            for row in fixture['files']:
                (root/row['path']).write_bytes(row['raw_utf8'].encode())
            event_obs=ap['provider_event']['rpc_observations'][0]
            def wrong_provider(body):
                for log in body['result']['logs']:
                    if len(log.get('topics',[]))==3 and int(log['topics'][1],16)==82343:
                        log['topics'][2]='0x'+'0'*24+'1'*40
            mutate_observation(acp,event_obs,change_body=wrong_provider)
            with self.assertRaises(ValueError):
                verify_public_service_identity(root,acp,canonical_acp)

            erc='eip155:56:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:113284'
            verifier=Mock(return_value={'registration_verified':True,'document':{}})
            result=verify_service_identity(root,'unchanged-legacy-proof',erc,chain_verifier=verifier)
            verifier.assert_called_once_with(root,'unchanged-legacy-proof',erc)
            self.assertTrue(result['chain_registration_verified'])
            self.assertEqual(result['registration_chain_id'],56)
            for value in ('mcp-registry:fi.ophis/mcp@latest','acp:virtuals:bad-uuid','https://unrelated.example/registry'):
                self.assertIsNone(normalize_reference(value))
            with self.assertRaisesRegex(ValueError,'ERC-8004'):
                _identity(canonical_mcp)


if __name__=='__main__':
    unittest.main()
