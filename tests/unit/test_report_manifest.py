from uuid import uuid4

import pytest
from pydantic import ValidationError
from reputation_core.models import ManifestDocument


@pytest.mark.parametrize(
    "path",
    [
        "report_core.json",
        "evidence_manifest.json",
        "anchor_receipt.json",
        "../policy.json",
        "/policy.json",
        "schemas/../policy.json",
        "C:/policy.json",
        "schemas\\policy.json",
    ],
)
def test_manifest_rejects_commitment_cycles_and_nonportable_paths(path):
    with pytest.raises(ValidationError):
        ManifestDocument(path=path, evidence_id=uuid4())
