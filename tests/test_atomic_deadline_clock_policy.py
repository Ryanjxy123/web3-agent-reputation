"""One real A21 calibration check; legacy replay is exercised when locally retained."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from reputation_core import Verdict
from reputation_core.reporting import parse_evaluation_report
from reputation_platform import atomic_swap_report as adapter
from reputation_platform.swap_report import SwapEvidence

ROOT=Path(__file__).resolve().parents[1]


class DeadlineClockMeasurementAcceptance(unittest.TestCase):
    def test_actual_request_interval_wrong_ttl_and_legacy_replay(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/atomic_deadline_clock_case.json').read_bytes())
        rows=[{'stage':x['stage'],'obs':x['observation'],'body':json.loads(x['raw_utf8']),
               'raw':x['raw_utf8'].encode(),'complete':True,
               'when':adapter._time(x['observation']['observed_at'])} for x in fixture['rows']]
        legacy=fixture['plan'];planned=fixture['planned']
        old,_=adapter._metrics(None,legacy,None,planned,{},rows)
        self.assertEqual(old['default-contract'][0],Verdict.FAIL)
        revised=dict(legacy,deadline_default_clock_policy='request-interval-v1')
        new,quote=adapter._metrics(None,revised,None,planned,{},rows)
        self.assertEqual(new['default-contract'][0],Verdict.UNKNOWN)
        self.assertEqual(new['default-contract'][2]['delta_seconds'],599)
        self.assertEqual(new['default-contract'][2]['possible_delta_seconds'],[595,601])
        self.assertEqual(new['default-contract'][2]['measurement_validity'],'unknown')
        self.assertEqual(new['complete-response'],old['complete-response'])
        self.assertEqual(new['intent-binding'],old['intent-binding'])
        issued=new['default-contract'][2]['provider_timestamp_seconds']
        for delta,expected in [(600,Verdict.PASS),(595,Verdict.UNKNOWN),(601,Verdict.UNKNOWN),
                               (570,Verdict.FAIL),(900,Verdict.FAIL)]:
            controlled=copy.deepcopy(quote)
            controlled['decoded']['deadlines'][0]['timestamp']=issued+delta
            self.assertEqual(adapter._deadline_default_clock(controlled,600)[0],expected)
        missing=copy.deepcopy(quote);missing['response']['obs']['elapsed_ms']=None
        self.assertEqual(adapter._deadline_default_clock(missing,600)[0],Verdict.UNKNOWN)
        # No marker continues to mean exact v1, even after v2 is evaluated.
        self.assertEqual(adapter._metrics(None,legacy,None,planned,{},rows)[0]['default-contract'][0],Verdict.FAIL)

        path=ROOT/fixture['legacy_report']
        if path.is_file():
            manifest_path=ROOT/fixture['legacy_manifest']
            prior={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in (path,manifest_path)}
            report=parse_evaluation_report(path.read_bytes())
            hashes={x['path']:x['sha256'] for x in json.loads(manifest_path.read_bytes())['inputs']}
            self.assertEqual(adapter.verify_atomic_swap_report_sources(ROOT,report,hashes),report.registration_reference)
            for name,digest in prior.items():self.assertEqual(hashlib.sha256(Path(name).read_bytes()).hexdigest(),digest)
            source_path=ROOT/fixture['corrected_source']
            if source_path.is_file():
                source=json.loads(source_path.read_bytes())
                revised_hashes={x['path']:x['sha256'] for x in source['sources']}
                revised_hashes[adapter.ADR]=hashlib.sha256((ROOT/adapter.ADR).read_bytes()).hexdigest()
                actual=adapter.replay_atomic_swap_sources(ROOT,SwapEvidence(ROOT,revised_hashes),source,report.generated_at)
                previous={(o.task_key,o.case_id,o.criterion_id):o.verdict for o in report.shared_assessment.observations}
                current={(o.task_key,o.case_id,o.criterion_id):o.verdict for o in actual.shared_assessment.observations}
                changed=[key for key in previous if previous[key]!=current[key]]
                self.assertEqual(len(changed),1)
                self.assertEqual(changed[0][0],planned['task_key'])
                self.assertEqual(changed[0][2],'default-contract')
                self.assertEqual(previous[changed[0]],Verdict.FAIL)
                self.assertEqual(current[changed[0]],Verdict.UNKNOWN)
                self.assertEqual(len(actual.shared_assessment.tasks),len(report.shared_assessment.tasks))
                print('Retained full v1 replay unchanged; corrected real-source verdict difference is A21 default-contract only.')
        else:
            print('Full retained artifact replay NOT_RUN in fixture-only environment; real A21 v1/v2 fixture checks ran.')


if __name__=='__main__':
    unittest.main()
