"""One offline real negative and attribution controls; no network or new task."""
import copy
import json
from pathlib import Path
import unittest
from reputation_core import Verdict
from reputation_platform import atomic_swap_report as adapter


class InvalidTypedServerErrorAcceptance(unittest.TestCase):
    def test_real_invalid_amount_500_breaks_frozen_error_contract_only(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/atomic_invalid_typed_5xx_case.json').read_bytes())
        class Evidence:
            def json(self,path):return fixture['schema']
        row={'complete':True,'obs':fixture['observation'],'body':fixture['response']}
        def verdict(value,planned=None):
            return adapter._metrics(Evidence(),fixture['plan'],None,planned or fixture['planned'],{},[value])[0]['safe-rejection'][0]
        self.assertEqual(verdict(row),Verdict.FAIL)
        for status,body,complete in [(500,{'error':'upstream failed'},True),(502,'<html>Bad gateway</html>',False),
                                      (403,fixture['response'],True),(None,None,False),
                                      (500,dict(fixture['response'],kind='success'),True)]:
            changed=copy.deepcopy(row);changed['obs']['http_status']=status;changed['body']=body;changed['complete']=complete
            self.assertEqual(verdict(changed),Verdict.UNKNOWN)
        unrelated=copy.deepcopy(row);unrelated['obs']['url']='https://unrelated.example/api/swap/quote'
        self.assertEqual(verdict(unrelated),Verdict.UNKNOWN)
        valid=copy.deepcopy(fixture['planned']);valid['requests'][0]['json']['sellAmount']='0.1'
        self.assertEqual(verdict(row,valid),Verdict.UNKNOWN)
        undeclared=copy.deepcopy(fixture['schema']);fixture['schema']['paths']['/api/swap/quote']['post']['responses']={}
        self.assertEqual(verdict(row),Verdict.UNKNOWN)
        fixture['schema']=undeclared


if __name__=='__main__':
    unittest.main()
