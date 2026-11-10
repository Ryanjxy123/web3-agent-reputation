"""One offline acceptance; controlled RPC/identity data are NOT public execution evidence."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from eth_hash.auto import keccak

from reputation_core import Verdict
from reputation_core.prediction_chain import calldata
from reputation_core.swap import encode_batch
from reputation_platform import atomic_swap_report as adapter
from reputation_platform.swap_report import SwapEvidence
from reputation_platform.atomic_swap_export import export_atomic_swap_sources
from reputation_platform.shared_report import verify_shared_report_sources
from reputation_platform.agent_profiles import profile_from_report
from reputation_platform.report_chain_view import build_report_chain_evidence
from reputation_platform.db import Repository

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / 'fixtures/atomic_swap_report_case.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def word(value):
    return value.to_bytes(32, 'big')


def returns(values):
    encoded = [word(len(x)) + x + bytes((-len(x)) % 32) for x in values]
    offset, offsets = len(values) * 32, []
    for value in encoded:
        offsets.append(word(offset)); offset += len(value)
    return '0x' + (word(32) + word(len(values)) + b''.join(offsets) + b''.join(encoded)).hex()


class OverlayEvidence(SwapEvidence):
    def __init__(self, evidence, overlay):
        self.overlay = {key: json.dumps(value).encode() for key, value in overlay.items()}
        super().__init__(evidence.root, dict(evidence.hashes, **{key: digest(raw) for key, raw in self.overlay.items()}))

    def raw(self, name):
        return self.overlay[name] if name in self.overlay else super().raw(name)


class AtomicReportAcceptance(unittest.TestCase):
    def test_frozen_http_atomic_effect_replay_and_critical_failure_boundaries(self):
        actual = json.loads(FIXTURE.read_text(encoding='utf8'))
        # Only the unsigned provider request/responses are retained real data.
        # Everything below involving RPC, identity or tx hashes is controlled
        # test input. It is never published or described as a chain integration.
        with tempfile.TemporaryDirectory(prefix='atomic-report-unit-', dir=ROOT/'runtime') as temporary:
            directory = Path(temporary)
            prefix = directory.relative_to(ROOT).as_posix()
            hashes = {adapter.ADR: digest((ROOT/adapter.ADR).read_bytes()),
                      'configs/generic-rpc.json': digest((ROOT/'configs/generic-rpc.json').read_bytes())}

            def save(name, value):
                raw = json.dumps(value, ensure_ascii=False).encode()
                path = directory/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
                relative = path.relative_to(ROOT).as_posix(); hashes[relative] = digest(raw)
                return relative

            def observed(name, url, method, request, response, status=200):
                body = save(name+'.response.json', response)
                return save(name+'.observation.json', {'url': url, 'method': method,
                    'request_json': json.dumps(request) if request is not None else None,
                    'observed_at': '2026-10-28T15:37:51+00:00', 'elapsed_ms': 25000.0,
                    'http_status': status, 'body_complete': True,
                    'error_kind': None if status == 200 else 'http_status_not_success',
                    'response_file': Path(body).name, 'response_sha256': hashes[body]})

            rpc_index = 0
            def rpc(method, params, value, name=None):
                nonlocal rpc_index
                rpc_index += 1
                return observed(name or 'rpc-'+str(rpc_index), 'https://mainnet.base.org', 'POST',
                    {'jsonrpc': '2.0', 'id': rpc_index, 'method': method, 'params': params},
                    {'jsonrpc': '2.0', 'id': rpc_index, 'result': value})

            requests = [{key: row[key] for key in ('url', 'method', 'json')} for row in actual['request_plan']['targets']]
            for row, stage in zip(requests, ('quote', 'build')): row['stage'] = stage
            declaration = save('schema-excerpt.json', actual['declaration_schema'])
            declaration_obs = observed('declaration', 'https://agents.topazdex.com/openapi.json', 'GET', None,
                                       actual['declaration_schema'])
            quote_obs = observed('quote', requests[0]['url'], 'POST', requests[0]['json'], actual['quote_response'])
            build_obs = observed('build', requests[1]['url'], 'POST', requests[1]['json'], actual['build_response'])
            data = actual['build_response']['data']
            owner, token, output = data['payer'].lower(), data['sellToken'].lower(), data['buyToken'].lower()
            amount, minimum = int(data['sellAmount']), int(data['minOut'])
            key, missing_key, reject_key = str(uuid4()), str(uuid4()), str(uuid4())
            atomic = {'chain_id': 8453, 'calls': actual['build_response']['transactions']}
            decoded = adapter.normalize_atomic_swap(atomic)
            calls = adapter.atomic_evidence_calls(atomic)
            self.assertEqual(len(calls), 16)
            self.assertEqual(calls[3:10], [{'target': x['to'], 'value': '0', 'data': x['data']} for x in decoded['calls']])
            self.assertEqual(len(adapter.atomic_post_calls(atomic)), 6)
            factory, implementation = ('0x' + x*40 for x in ('4', '5'))
            pool = adapter.predict_slipstream_pool(factory, implementation, token, output, 50)
            self.assertEqual(adapter.predict_slipstream_pool(
                '0xaa5865dC3A60b25D305226d66fd573021f0D8fFB',
                '0x2DaA7cF731334b4Cd1c2E4E01E97Ca67F4B9C6AE', token, output, 50),
                actual['build_response']['data']['routes'][0]['hops'][0]['address'].lower())
            roles = {'router': decoded['router'], 'permit2': decoded['permit2'], 'executor': owner,
                     'cl_factory': factory, 'cl_implementation': implementation}
            codes = {role: '0x600060'+format(i, '02x') for i, role in enumerate(roles)}
            binding_source = save('controlled-code-review.json', {'fixture_only': True, 'not_a_public_deployment': True})
            binding = {'chain_id': 8453, 'router': decoded['router'], 'permit2': decoded['permit2'],
                'cl_factory': factory, 'cl_implementation': implementation,
                'runtime_keccak': {role: '0x'+keccak(bytes.fromhex(code[2:])).hex() for role, code in codes.items()},
                'source_refs': [{'path': binding_source, 'sha256': hashes[binding_source]}]}
            expected = {'token_in': token, 'token_out': output, 'amount_in': str(amount), 'recipient': owner,
                        'slippage_bps': 50, 'safe_rejection': False}
            invalid_request = copy.deepcopy(requests[0]); invalid_request['json']['sellAmount'] = '0'
            reject_obs = observed('reject', invalid_request['url'], 'POST', invalid_request['json'],
                                  {'error': 'sellAmount must be positive'}, 400)
            service = 'https://agents.topazdex.com/agent.json'
            canonical = 'eip155:56:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:113284'
            tasks = [
                {'task_id': 'unit-normal', 'task_key': key, 'requests': requests, 'expected': expected,
                 'input_summary': 'Controlled offline normal task, two HTTP stages', 'planned_actual_execution': True},
                {'task_id': 'unit-missing', 'task_key': missing_key, 'requests': requests, 'expected': expected,
                 'input_summary': 'Controlled unobserved future slot', 'planned_actual_execution': False},
                {'task_id': 'unit-reject', 'task_key': reject_key, 'requests': [invalid_request],
                 'expected': dict(expected, amount_in='0', safe_rejection=True, invalid_field='sellAmount', rejection_statuses=[400, 422]),
                 'input_summary': 'Controlled invalid amount task', 'planned_actual_execution': False},
            ]
            case = lambda name, dim, criterion, members, group=None, normal=False: {
                'case_id': name, 'dimension': dim, 'declaration_group_id': group, 'title': name,
                'criterion_ids': [criterion], 'planned_task_ids': members, 'normal_execution': normal, 'required_decisive': 1}
            campaign = {'schema_version': 'atomic-swap-campaign-v1', 'status': 'FROZEN',
                'frozen_at': '2026-10-28T15:00:00+00:00', 'candidate_key': 'unit-not-public', 'name': 'Controlled unit inputs',
                'registration_reference': canonical, 'registered_service': service, 'chain_id': 8453, 'executor': owner,
                'scope': 'Controlled unit scope only', 'scope_exclusions': ['No public execution claim'],
                'source_snapshot': {'path': declaration, 'sha256': hashes[declaration], 'observation': declaration_obs},
                'response_mapping': {'calls_pointer': '/transactions', 'fields': {
                    'token_in': '/data/sellToken', 'token_out': '/data/buyToken', 'amount_in': '/data/sellAmount',
                    'recipient': '/data/payer', 'minimum_out': '/data/minOut', 'quoted_out': '/data/expectedOut',
                    'chain_id': '/chainId', 'slippage_bps': '/data/topazApiQuote/slippageBips', 'issued_at': '/timestamp'},
                    'rejection_error_pointer': '/error'},
                'scoring_contract': {'policy': 'transaction-agent-evidence-v3', 'shared_schema': 'shared-task-assessment-v3',
                    'weights': {'availability': 30, 'functional': 40, 'behavioral': 30},
                    'minimum_confirmation_distance': 64, 'response_sla_ms': None},
                'protocol_binding': binding, 'tasks': tasks,
                'capability': {'capability_id': 'atomic-erc20-swap', 'title': 'Controlled atomic scope', 'selected': True,
                    'write_operation': True, 'declaration_groups': [
                        {'group_id': x, 'title': x, 'selected': True, 'source_references': [declaration]}
                        for x in ('intent', 'safety', 'effect', 'rejection')] + [
                        {'group_id': 'unselected', 'title': 'Not selected', 'selected': False, 'source_references': [declaration]}]},
                'cases': [case('a', 'availability', 'complete-response', ['unit-normal','unit-missing']),
                    case('fi', 'functional', 'intent-binding', ['unit-normal','unit-missing'], 'intent'),
                    case('fs', 'functional', 'call-safety', ['unit-normal'], 'safety'),
                    case('fe', 'functional', 'execution-effect', ['unit-normal'], 'effect'),
                    case('fr', 'functional', 'safe-rejection', ['unit-reject'], 'rejection'),
                    case('b', 'behavioral', 'onchain-fulfillment', ['unit-normal'], normal=True)]}
            plan_path = save('campaign.json', campaign)
            config_ref = {'path': 'configs/generic-rpc.json', 'sha256': hashes['configs/generic-rpc.json']}
            identity_path = save('controlled-identity.json', {'fixture_only': True, 'source_refs': [config_ref]})
            sim_plan = {'task_key': key, 'chain_id': 8453, 'payer': owner,
                'source_response_sha256': hashes[build_obs.replace('.observation.json','.response.json')], 'calls': calls}
            sim_path = save('simulation-plan.json', sim_plan)
            block = actual['build_response']['data']['topazApiQuote']['blockNumber']
            tag, block_hash, tx_block_hash, tx_hash = hex(block), '0x'+'1'*64, '0x'+'2'*64, '0x'+'3'*64
            timestamp = int(datetime.fromisoformat(actual['build_response']['timestamp'].replace('Z','+00:00')).timestamp())
            sim_refs = [rpc('eth_chainId', [], hex(8453)), rpc('eth_getBlockByNumber', [tag, False],
                {'number': tag, 'hash': block_hash, 'timestamp': hex(timestamp), 'transactions': []})]
            for role, target in roles.items(): sim_refs.append(rpc('eth_getCode', [target, tag], codes[role]))
            sim_refs.append(rpc('eth_getCode', [pool, tag],
                '0x363d3d373d3d3d363d73'+implementation[2:]+'5af43d82803e903d91602b57fd5bf3'))
            tokens = sorted([token, output])
            sim_refs.append(rpc('eth_call', [{'to': factory, 'data': calldata('getPool(address,address,int24)', *tokens, 50)}, tag],
                                '0x'+word(int(pool,16)).hex()))
            for signature, value in [('token0()',int(tokens[0],16)),('token1()',int(tokens[1],16)),('tickSpacing()',50)]:
                sim_refs.append(rpc('eth_call', [{'to':pool,'data':calldata(signature)},tag], '0x'+word(value).hex()))
            credit = minimum + 1000
            before, after = [1_000_000, 0, 0], [1_000_000-amount, credit, 0]
            results = [*(word(x) for x in before), *(b'' for _ in range(7)), *(word(x) for x in after), word(0), word(0), bytes(96)]
            sim_call = rpc('eth_call', [{'from':owner,'to':owner,'data':encode_batch(calls),'value':'0x0'},tag],
                           returns(results), 'complete-simulation')
            sim_refs.append(sim_call)
            actual_tx = {'chainId':8453,'from':owner,'to':owner,'data':encode_batch(calls),'value':'0','nonce':7}
            intent_path = save('controlled-execution-intent.json', {'fixture_only':True,'task_key':key,
                'plan_sha256':hashes[sim_path], 'simulation_plan_sha256':hashes[sim_path], 'fixed_block':block,
                'block_hash':block_hash,'transaction':actual_tx})
            transaction = dict(actual_tx, chainId=hex(8453), value='0x0', nonce='0x7', hash=tx_hash,
                input=actual_tx['data'], blockHash=tx_block_hash, blockNumber=hex(block+1), transactionIndex='0x0')
            transaction.pop('data')
            topic = lambda value: '0x'+word(int(value,16)).hex()
            transfer = adapter.retained.TRANSFER
            def log(token_address, sender, recipient, quantity, index):
                return {'address':token_address,'topics':[transfer,topic(sender),topic(recipient)],'data':'0x'+word(quantity).hex(),
                    'transactionHash':tx_hash,'blockHash':tx_block_hash,'blockNumber':hex(block+1),
                    'transactionIndex':'0x0','logIndex':hex(index),'removed':False}
            receipt = {'transactionHash':tx_hash,'blockHash':tx_block_hash,'blockNumber':hex(block+1),
                'transactionIndex':'0x0','from':owner,'to':owner,'status':'0x1',
                'logs':[log(token,owner,pool,amount,0),log(output,pool,owner,credit,1)]}
            execution_refs = [rpc('eth_chainId', [], hex(8453)),rpc('eth_getTransactionByHash',[tx_hash],transaction,'actual-transaction'),
                rpc('eth_getTransactionReceipt',[tx_hash],receipt,'receipt'),rpc('eth_getBlockByNumber',[hex(block+1),False],
                    {'number':hex(block+1),'hash':tx_block_hash,'timestamp':hex(timestamp+2),'transactions':[tx_hash]},'canonical-block'),
                rpc('eth_blockNumber',[],hex(block+65),'head'),rpc('eth_getCode',[owner,hex(block+1)],codes['executor']),
                rpc('eth_call',[{'from':owner,'to':owner,'data':encode_batch(adapter.atomic_post_calls(atomic)),'value':'0x0'},hex(block+1)],
                    returns([*(word(x) for x in after),word(0),word(0),bytes(96)]),'post-state')]
            item = {'task_key':key,'http_observations':[quote_obs,build_obs],
                'simulation':{'plan':sim_path,'rpc_observations':sim_refs,'call_label':'complete-simulation'},
                'execution':{'plan':sim_path,'intent_path':intent_path,'payer':owner,'transaction_hash':tx_hash,'rpc_observations':execution_refs}}
            source = {'schema_version':'atomic-swap-evidence-v1','adapter':adapter.ADAPTER,'candidate_key':campaign['candidate_key'],
                'name':campaign['name'],'registration_reference':canonical,'registered_service':service,
                'registration_proof':identity_path,'campaign_plan':plan_path,
                'tasks':[item,{'task_key':reject_key,'http_observations':[reject_obs]}],
                'sources':[{'path':name,'sha256':sha} for name,sha in hashes.items()]}
            source_path = save('source.json', source)
            evidence = SwapEvidence(ROOT, hashes)
            generated = datetime(2026,10,29,tzinfo=timezone.utc)
            controlled_identity = {'registration_verified':True,'document':{'services':[{'endpoint':service}]}}

            def replay(reader=evidence, value=source):
                with patch.object(adapter,'verify_registration_proof',return_value=controlled_identity):
                    return adapter.replay_atomic_swap_sources(ROOT,reader,value,generated)

            report = replay()
            self.assertEqual(report.shared_assessment.result.task_count,3)
            self.assertEqual(len(report.shared_assessment.tasks),3)  # two HTTP stages still one task
            metric = lambda r,name:next(x for x in r.shared_assessment.observations if x.task_key==key and x.criterion_id==name)
            for name in ('complete-response','intent-binding','call-safety','execution-effect','onchain-fulfillment'):
                self.assertEqual(metric(report,name).verdict,Verdict.PASS)
            self.assertEqual(metric(report,'complete-response').elapsed_ms,50000.0)
            self.assertEqual(report.shared_assessment.result.availability.counts.not_run,1)
            self.assertEqual(next(x for x in report.shared_assessment.observations if x.task_key==reject_key).verdict,Verdict.PASS)
            self.assertIsNotNone(report.scores.overall)

            no_execution=copy.deepcopy(source);no_execution['tasks'][0].pop('execution')
            no_b=replay(value=no_execution)
            self.assertEqual(metric(no_b,'onchain-fulfillment').verdict,Verdict.UNKNOWN)
            self.assertIsNone(no_b.scores.overall)

            def response_overlay(observation, result):
                obs=evidence.json(observation);response=(Path(observation).parent/obs['response_file']).as_posix()
                packet=evidence.json(response);packet['result']=result
                obs['response_sha256']=digest(json.dumps(packet).encode())
                return {observation:obs,response:packet}

            # Head is genuinely pending in this controlled fixture: no B fail.
            changed=OverlayEvidence(evidence,response_overlay(execution_refs[4],hex(block+64)))
            self.assertEqual(metric(replay(changed),'onchain-fulfillment').verdict,Verdict.UNKNOWN)
            # Old Router output cannot subsidize the simulated minimum.
            contaminated=list(results);contaminated[2]=word(credit)
            changed=OverlayEvidence(evidence,response_overlay(sim_call,returns(contaminated)))
            self.assertEqual(metric(replay(changed),'execution-effect').verdict,Verdict.UNKNOWN)
            self.assertEqual(metric(replay(changed),'execution-effect').measurement_validity,'invalid')
            # Real canonical output below the goal is a B failure, not a fee pass.
            bad=copy.deepcopy(receipt);bad['logs'][1]['data']='0x'+word(minimum-1).hex()
            overlay=response_overlay(execution_refs[2],bad)
            overlay.update(response_overlay(execution_refs[-1],returns([word(after[0]),word(minimum-1),word(0),word(0),word(0),bytes(96)])))
            failed=replay(OverlayEvidence(evidence,overlay))
            self.assertEqual(metric(failed,'onchain-fulfillment').verdict,Verdict.FAIL)
            self.assertFalse(metric(failed,'onchain-fulfillment').critical)
            # Three independent final allowances must all be zero.
            changed=OverlayEvidence(evidence,response_overlay(execution_refs[-1],
                returns([*(word(x) for x in after),word(0),word(0),word(1)+bytes(64)])))
            self.assertEqual(metric(replay(changed),'onchain-fulfillment').verdict,Verdict.FAIL)

            draft=copy.deepcopy(campaign);draft['status']='DRAFT'
            with self.assertRaisesRegex(ValueError,'frozen'):
                replay(OverlayEvidence(evidence,{plan_path:draft}))
            unfilled=copy.deepcopy(campaign);unfilled['protocol_binding']['runtime_keccak']['router']=None
            with self.assertRaisesRegex(ValueError,'unfilled or unreviewed'):
                replay(OverlayEvidence(evidence,{plan_path:unfilled}))
            preparation=copy.deepcopy(campaign)
            preparation['protocol_binding']['status']='PREPARATION_NOT_FROZEN_NOT_CHAIN_VERIFIED'
            with self.assertRaisesRegex(ValueError,'unfilled or unreviewed'):
                replay(OverlayEvidence(evidence,{plan_path:preparation}))
            late=copy.deepcopy(campaign);late['frozen_at']='2026-10-29T00:00:00+00:00'
            with self.assertRaisesRegex(ValueError,'predates'):
                replay(OverlayEvidence(evidence,{plan_path:late}))
            duplicate=copy.deepcopy(source);duplicate['tasks'].append(dict(item,task_key=missing_key,http_observations=[]))
            with self.assertRaisesRegex(ValueError,'transaction cannot supply two tasks'):
                replay(value=duplicate)
            corrupted=copy.deepcopy(evidence.json(build_obs));corrupted['request_json']='{}'
            with self.assertRaisesRegex(ValueError,'frozen request'):
                replay(OverlayEvidence(evidence,{build_obs:corrupted}))
            raw_path=directory/'build.response.json';old=raw_path.read_bytes();raw_path.write_bytes(old+b' ')
            with self.assertRaises(ValueError):replay()
            raw_path.write_bytes(old)

            # Exercise the artifact builder/origin verifier with immutable software
            # text snapshots; no live services/*.py is a manifest dependency.
            with patch.object(adapter,'verify_registration_proof',return_value=controlled_identity):
                built=adapter.build_atomic_swap_report(ROOT,Path(source_path),Path(prefix)/'report')
                manifest=json.loads((directory/'report/manifest.json').read_bytes())
                published_hashes={x['path']:x['sha256'] for x in manifest['inputs']}
                self.assertTrue(any('/software/' in x for x in published_hashes))
                self.assertFalse(any(x.startswith('services/') and x.endswith('.py') for x in published_hashes))
                self.assertEqual(adapter.verify_atomic_swap_report_sources(ROOT,built,published_hashes),canonical)
                self.assertEqual(verify_shared_report_sources(ROOT,built,published_hashes),canonical)
                imported=Repository('unused-no-database',ROOT)._load_report(directory/'report')
                self.assertEqual(imported.registration_reference,canonical)
                profile=profile_from_report(ROOT,{'validated_json':built.model_dump(mode='json'),
                    'registration_reference':canonical,'source_directory':prefix+'/report',
                    'manifest_sha256':digest((directory/'report/manifest.json').read_bytes())})
                self.assertEqual(profile.execution_accounts,[owner])
                self.assertEqual(profile.registration_chain_id,56)
                view=build_report_chain_evidence(ROOT,built,imported.evidence_files,key)
                self.assertEqual(len(view.actions),16)
                self.assertEqual(sum(action.action=='swap' for action in view.actions),1)
                self.assertTrue(all(action.transaction_hash==tx_hash for action in view.actions))
                with self.assertRaisesRegex(ValueError,'differs from evidence replay'):
                    adapter.verify_atomic_swap_report_sources(ROOT,built.model_copy(update={'scope':'tampered'}),published_hashes)

                # Append-only plan clocks preserve old observations; an unobserved
                # new slot remains UNKNOWN and cannot inflate the real HTTP count.
                appended=copy.deepcopy(campaign)
                new_slot=copy.deepcopy(tasks[1]);new_slot.update(task_id='unit-appended',task_key=str(uuid4()))
                appended['tasks'].append(new_slot)
                appended['cases'][0]['planned_task_ids'].append(new_slot['task_id'])
                appended['previous_plan']={'path':plan_path,'sha256':hashes[plan_path]}
                appended['frozen_at']='2026-10-29T00:00:00+00:00'
                appended['scope']+='; appended slot'
                appended_path=save('campaign-v2.json',appended)
                mapping_path=save('http-map.json',{'campaign_plan':plan_path,'tasks':source['tasks']})
                save('tasks/'+key+'/atomic-execution/run/proof-rpc-controlled/source-item-execution.json',item)
                exported=export_atomic_swap_sources(ROOT,plan=appended_path,plan_sha256=hashes[appended_path],
                    registration_proof=identity_path,http_map=mapping_path,output=prefix+'/export')
                self.assertEqual(exported['planned_task_slots'],4)
                self.assertEqual(exported['tasks_with_http_response'],2)
                self.assertEqual(exported['execution_source_items'],1)
                public_source=json.loads((directory/'export/source.json').read_bytes())
                self.assertFalse(any('.private' in row['path'] for row in public_source['sources']))
                later=adapter.build_atomic_swap_report(ROOT,Path(prefix)/'export/source.json',Path(prefix)/'export-report')
                self.assertEqual(later.shared_assessment.result.task_count,4)
                self.assertEqual(sum(task.observed_at is not None for task in later.shared_assessment.tasks),2)
                self.assertIn('2个已采业务任务，4个冻结任务槽位',(directory/'export-report/report.html').read_text(encoding='utf8'))
                forged=copy.deepcopy(appended);forged['tasks'][0]['expected']['amount_in']='1'
                with self.assertRaisesRegex(ValueError,'changed or removed'):
                    adapter._campaign_lineage(OverlayEvidence(SwapEvidence(ROOT,hashes),{appended_path:forged}),appended_path)


if __name__ == '__main__':
    unittest.main()
