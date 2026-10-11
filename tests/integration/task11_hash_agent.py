"""Experiment-only Agent: sign a real write with the wrong digest, claim the requested one."""
from unittest.mock import patch

from fixture_agents import service


class HashMismatchAgent(service.Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        real_contract = self.web3.eth.contract

        def wrong_digest_contract(*contract_args, **contract_kwargs):
            contract = real_contract(*contract_args, **contract_kwargs)
            anchor = contract.functions.anchorRecord

            def anchor_wrong_digest(request_id, record_hash):
                wrong_hash = "0x" + ("11" if record_hash != "0x" + "11" * 32 else "22") * 32
                return anchor(request_id, wrong_hash)

            contract.functions.anchorRecord = anchor_wrong_digest
            return contract

        self.web3.eth.contract = wrong_digest_contract


def create_app():
    with patch.object(service, "Agent", HashMismatchAgent):
        return service.create_app()
