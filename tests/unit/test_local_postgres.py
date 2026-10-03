from types import SimpleNamespace

import pytest

from scripts import local_postgres


def test_runtime_alias_reuses_target_and_rejects_collision(tmp_path, monkeypatch):
    monkeypatch.setattr(
        local_postgres, "os", SimpleNamespace(name="nt", path=local_postgres.os.path)
    )
    monkeypatch.setattr(local_postgres, "RUNTIME", tmp_path)
    monkeypatch.setattr(local_postgres, "WINDOWS_RUNTIME", tmp_path)
    assert local_postgres.runtime_alias().samefile(tmp_path)

    collision = tmp_path / "occupied"
    collision.mkdir()
    monkeypatch.setattr(local_postgres, "WINDOWS_RUNTIME", collision)
    with pytest.raises(RuntimeError, match="another directory"):
        local_postgres.runtime_alias()

    monkeypatch.setattr(local_postgres, "os", SimpleNamespace(name="posix"))
    assert local_postgres.runtime_alias() == tmp_path
