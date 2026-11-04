import pytest
from urllib.parse import urljoin
@pytest.fixture
def httpbin(httpbin):
    httpbin_url = httpbin.url.rstrip('/') + '/'
    def inner(*suffix):
        return urljoin(httpbin_url, '/'.join(suffix))
    return inner
def test_collect_only(httpbin):
    raise AssertionError('This body must never execute')
