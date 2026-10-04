import hashlib
import os

import pytest

from scripts import download_models_v030 as download


def test_small_files_require_official_git_blob_identity_and_record_mtime(tmp_path):
    data = b'{"tokenizer":"frozen"}\n'
    path = tmp_path / 'tokenizer_config.json'
    path.write_bytes(data)
    frozen = {'bytes': len(data), 'lfs': None,
              'blob_id': hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()}
    record = download.verify_file(path, frozen)
    assert record == {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                      'mtime_ns': path.stat().st_mtime_ns}
    path.write_bytes(data.replace(b'frozen', b'broken'))
    with pytest.raises(ValueError, match='Git blob identity'):
        download.verify_file(path, frozen)


def test_transport_requires_fixed_repo_full_sha_size_and_revision():
    candidate = 'swe-next-14b'
    name = 'model-00001-of-00006.safetensors'
    selected = {name: {'bytes': 20, 'lfs': {'sha256': 'f' * 64}}}
    row = {'Name': name, 'Size': 20, 'Sha256': 'f' * 64,
           'Revision': download.MS_WEIGHT_REVISIONS[candidate]}
    snapshot = {'repo': download.MODELS[candidate][0], 'domain': 'modelscope.cn',
                'status': 200, 'payload': {'Data': {'Files': [row]}}}
    assert download.transport_files(candidate, snapshot, selected)[name] == row
    for key, value, error in [('Sha256', 'a' * 64, 'content identity'),
                              ('Size', 21, 'content identity'),
                              ('Revision', 'master', 'revision')]:
        old = row[key]
        row[key] = value
        with pytest.raises(ValueError, match=error):
            download.transport_files(candidate, snapshot, selected)
        row[key] = old
    snapshot['repo'] = 'unrelated/other-model'
    with pytest.raises(ValueError, match='same-name official source'):
        download.transport_files(candidate, snapshot, selected)


class Response:
    def __init__(self, body, *, status=206, content_range='bytes 2-5/8'):
        self.body = body
        self.status_code = status
        self.headers = {'Content-Range': content_range}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.body


class Session:
    def __init__(self, response):
        self.response = response

    def get(self, url, **kwargs):
        assert kwargs['headers'] == {'Range': 'bytes=2-5'}
        return self.response


@pytest.mark.parametrize('response,error', [
    (Response(b'abcd', status=200), 'exact requested range'),
    (Response(b'abcd', content_range='bytes 0-3/8'), 'exact requested range'),
    (Response(b'abcd', content_range='bytes 2-5/9'), 'exact requested range'),
    (Response(b'abc'), 'ended before'),
    (Response(b'abcde'), 'exceeded declared'),
])
def test_range_refuses_wrong_headers_lengths_and_overrun(tmp_path, response, error):
    path = tmp_path / 'partial'
    path.write_bytes(b'00000000')
    fd = os.open(path, os.O_RDWR)
    try:
        with pytest.raises(ValueError, match=error):
            download.stream_range(Session(response), 'https://example.invalid', 2, 5, 8, fd)
    finally:
        os.close(fd)
    assert path.stat().st_size == 8


def test_exact_range_preserves_other_bytes_but_does_not_prove_full_sha(tmp_path):
    path = tmp_path / 'partial'
    path.write_bytes(b'00000000')
    fd = os.open(path, os.O_RDWR)
    try:
        digest = download.stream_range(Session(Response(b'abcd')), 'https://example.invalid',
                                       2, 5, 8, fd)
    finally:
        os.close(fd)
    assert path.read_bytes() == b'00abcd00'
    assert digest == hashlib.sha256(b'abcd').hexdigest()
    with pytest.raises(ValueError, match='LFS content identity'):
        download.verify_file(path, {'bytes': 8, 'lfs': {'sha256': hashlib.sha256(b'xxabcdyy').hexdigest()}})
