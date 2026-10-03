from zipfile import ZipFile

import pytest
from reputation_verifier import VerificationError, verify_bundle


def test_verifier_rejects_path_traversal(tmp_path):
    path = tmp_path / "unsafe.zip"
    with ZipFile(path, "w") as archive:
        archive.writestr("../report_core.json", b"{}")
    with pytest.raises(VerificationError) as failure:
        verify_bundle(str(path))
    assert failure.value.code == "UNSAFE_ARCHIVE"
