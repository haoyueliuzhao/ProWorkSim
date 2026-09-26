import hashlib
import os

from scripts.download_candidate_v015 import RangeJournal


def test_preallocated_length_is_not_progress_and_corrupt_ranges_resume(tmp_path):
    part = tmp_path / 'weight.partial'
    expected = b'a' * 8192 + b'b' * 8192
    sha = hashlib.sha256(expected).hexdigest()
    journal = RangeJournal(part, size=len(expected), expected_sha256=sha, chunk_bytes=8192)
    assert part.stat().st_size == len(expected)
    assert journal.pending() == [(0, 8191), (8192, 16383)]
    os.pwrite(journal.fd, expected[:8192], 0)
    journal.commit(0, 8191, hashlib.sha256(expected[:8192]).hexdigest())
    journal.close()
    resumed = RangeJournal(part, size=len(expected), expected_sha256=sha, chunk_bytes=8192)
    assert resumed.pending() == [(8192, 16383)]
    os.pwrite(resumed.fd, b'corrupt', 0)
    resumed.close()
    again = RangeJournal(part, size=len(expected), expected_sha256=sha, chunk_bytes=8192)
    assert again.pending() == [(0, 8191), (8192, 16383)]
    again.close()
