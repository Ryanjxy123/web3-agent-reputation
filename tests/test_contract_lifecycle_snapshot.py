"""One offline acceptance over the actual published contract-supplement package."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from reputation_core.admission import Verdict
from reputation_platform.contract_lifecycle_snapshot import restore_snapshot, verify_snapshot
from reputation_platform.contract_lifecycle_evidence import replay_contract_lifecycle

ROOT=Path(__file__).resolve().parents[1]
TRANSFER='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class ContractLifecycleSnapshotAcceptance(unittest.TestCase):
    def test_real_package_replay_and_refund_binding(self):
        archive=ROOT/os.environ.get('CONTRACT_LIFECYCLE_ARCHIVE','data/public-chain-mangoswap-v4-v1.tar.gz')
        supplied=os.environ.get('CONTRACT_LIFECYCLE_SNAPSHOT_DIR')
        (ROOT/'runtime').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='contract-lifecycle-acceptance-',dir=ROOT/'runtime') as temporary:
            scratch=Path(temporary)
            self.assertTrue(scratch.resolve().is_relative_to((ROOT/'runtime').resolve()))
            if supplied:
                source=(ROOT/supplied).resolve()
                review,source_hashes,_=verify_snapshot(ROOT,source)
                for name in [*source_hashes,*(str((source/name).relative_to(ROOT)).replace('\\','/')
                                             for name in ('snapshot.json','manifest.json'))]:
                    target=scratch/name;target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(ROOT/name,target)
                directory=scratch/source.relative_to(ROOT)
            else:
                self.assertTrue(archive.is_file(),'Real supplement archive required; no fixture or mock substitute')
                directory,review=restore_snapshot(scratch,archive)
            manifest=json.loads((directory/'manifest.json').read_bytes())
            hashes={item['path']:item['sha256'] for item in manifest['inputs']}
            config=json.loads((scratch/manifest['configuration']).read_bytes())
            parent=scratch/config['identity_report'];parent_before=parent.read_bytes()
            parent_data=json.loads(parent_before)
            self.assertEqual(parent_data['shared_assessment']['result']['task_count'],31)
            self.assertEqual(parent_data['shared_assessment']['result']['overall'],{'lower':77.25,'upper':87.98})
            self.assertEqual(len(review.actions),3)
            self.assertEqual(len({action.transaction_hash for action in review.actions}),3)
            self.assertTrue(all(action.verdict==Verdict.PASS for action in review.actions))
            availability=next(item for item in review.dimensions if item.purpose=='availability')
            self.assertEqual((availability.verdict,availability.observed),(Verdict.UNKNOWN,0))
            self.assertNotIn('scores',review.model_dump(mode='json'))
            facts,_,_=replay_contract_lifecycle(scratch,config,hashes)
            self.assertEqual({row['kind'] for row in facts['tasks']},{'native_swap','scheduled_cancel','limit_cancel'})
            for row in facts['tasks']:
                if row['kind'] in ('scheduled_cancel','limit_cancel'):
                    self.assertEqual(str(row['refunded_raw']),'20000')
                    self.assertEqual(str(row['remaining_allowance_raw']),'0')

            # Change a real refund log, then update every matching observation
            # and digest. Rejection must come from business checks, not SHA alone.
            target_task=next(item for item in config['tasks'] if item['kind']=='scheduled_cancel')
            protocol=json.loads((scratch/config['protocol_config']).read_bytes())
            topic=lambda value:'0x'+value[2:].lower().rjust(64,'0')
            altered_hashes=dict(hashes)
            backups={}
            changed=0
            for name in target_task['rpc_observations']:
                path=scratch/name;observation=json.loads(path.read_bytes())
                request=json.loads(observation['request_json'])
                if (request['method']!='eth_getTransactionReceipt'
                        or request['params']!=[target_task['transaction_hash']]
                        or not observation.get('response_file')):
                    continue
                response_path=path.parent/observation['response_file']
                raw=backups.get(response_path,response_path.read_bytes());response=json.loads(raw)
                if response.get('error') or not response.get('result'):
                    continue
                found=0
                for log in response['result']['logs']:
                    if (log['address'].lower()==protocol['token'].lower()
                            and [value.lower() for value in log.get('topics',[])]==[
                                TRANSFER,topic(protocol['contract']),topic(protocol['wallet'])]):
                        self.assertEqual(int(log['data'],16),20000)
                        log['data']='0x'+format(19999,'064x');found+=1
                changed+=found
                if not found:
                    continue
                backups.setdefault(response_path,raw)
                backups.setdefault(path,path.read_bytes())
                rewritten=(json.dumps(response,separators=(',',':'))+'\n').encode()
                response_path.write_bytes(rewritten)
                observation['response_sha256']=digest(rewritten)
                path.write_text(json.dumps(observation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                altered_hashes[response_path.relative_to(scratch).as_posix()]=digest(rewritten)
                altered_hashes[name]=digest(path.read_bytes())
            self.assertGreater(changed,0,'Actual cancellation refund receipt must be present')
            try:
                altered,checks,actions=replay_contract_lifecycle(scratch,config,altered_hashes)
            except ValueError as error:
                self.assertRegex(str(error).lower(),r'refund|退款|本金|transfer|转账|资金|资产')
                self.assertNotRegex(str(error).lower(),r'digest mismatch|sha256|source changed')
            else:
                target_actions=[item for item in actions if item.transaction_hash==target_task['transaction_hash']]
                self.assertFalse(any(item.verdict==Verdict.PASS for item in target_actions))
                unresolved=next(item for item in altered['tasks'] if item['task_key']==target_task['task_key'])
                self.assertIs(unresolved.get('verified'),False)
                self.assertRegex(unresolved['reason'].lower(),r'refund|退款|本金|transfer|转账|资金|资产')
                self.assertTrue(any(item.verdict==Verdict.UNKNOWN and target_task['task_key'] in item.explanation
                                    for item in checks))
            finally:
                for path,raw in backups.items():
                    path.write_bytes(raw)

            wrong_identity=deepcopy(config)
            wrong_identity['registration_reference']=config['registration_reference'].rsplit(':',1)[0]+':26346'
            with self.assertRaises(ValueError):
                replay_contract_lifecycle(scratch,wrong_identity,hashes)
            wrong_transaction=deepcopy(config)
            wrong_transaction['tasks'][0]['transaction_hash']=wrong_transaction['tasks'][1]['transaction_hash']
            wrong,_,wrong_actions=replay_contract_lifecycle(scratch,wrong_transaction,hashes)
            wrong_key=wrong_transaction['tasks'][0]['task_key']
            self.assertIs(next(item for item in wrong['tasks'] if item['task_key']==wrong_key).get('verified'),False)
            self.assertFalse(any(action.sample_id=='contract:'+wrong_key and action.verdict==Verdict.PASS
                                 for action in wrong_actions))
            self.assertEqual(parent.read_bytes(),parent_before,'Old shared report must remain byte-identical')
