import datetime as dt

import pytest

REF_DATE = dt.date(2026, 9, 10)


@pytest.fixture
def today() -> dt.date:
    return REF_DATE
