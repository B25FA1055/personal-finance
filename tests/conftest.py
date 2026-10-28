from pathlib import Path

import pytest

from make_fixture import build


@pytest.fixture
def xac_file(tmp_path: Path) -> Path:
    return build(tmp_path / "sample_xac.xlsx")
