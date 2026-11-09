import os
import tempfile

# Must be set before app.main is imported: tests use an isolated throw-away database.
_tmp = tempfile.mkdtemp(prefix="athar-test-")
os.environ["ATHAR_DB"] = os.path.join(_tmp, "test.db")
os.environ.pop("ATHAR_API_TOKEN", None)
os.environ.pop("ATHAR_AI_PROVIDER", None)

import pytest  # noqa: E402

from app import main  # noqa: E402
from app.analysis import DEFAULT_CONFIG  # noqa: E402
from app.security import RateLimiter  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state():
    """Every test starts from the sample environment, default scoring weights, empty undo history and a fresh limiter."""
    for var in ("ATHAR_MODE", "ATHAR_ADMIN_TOKEN", "ATHAR_API_TOKEN", "ATHAR_TRUST_PROXY"):
        os.environ.pop(var, None)
    if main.state.config != DEFAULT_CONFIG:
        main.state.set_config(DEFAULT_CONFIG)
    main.state.reset()
    main.state.history.clear()
    main.limiter = RateLimiter(read=10_000, write=10_000, explain=10_000)
    yield
