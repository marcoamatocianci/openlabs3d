import pytest
@pytest.fixture(autouse=True)
def reset_rate_limit_between_tests():
    from app.main import rate
    rate.clear()
    yield
    rate.clear()
