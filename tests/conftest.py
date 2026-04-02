from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def tmp_path() -> Path:
    base_dir = Path(__file__).resolve().parents[1] / ".tmp" / "testcases"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"case-{uuid4().hex}"
    path.mkdir()
    return path
