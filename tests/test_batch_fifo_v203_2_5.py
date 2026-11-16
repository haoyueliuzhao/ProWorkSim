import time
import pytest
from proworksim.software_batch_fifo_v203_2_5 import BatchFifo
from proworksim.software_benchmark_exact_transport_v054 import HTTPFailure

def test_unexpected_backend_error_is_returned_without_a_long_hang_or_retry(tmp_path):
    calls=[]
    def backend(route,payload):
        calls.append(route);raise ValueError('controlled local backend failure')
    fifo=BatchFifo(tmp_path/'fifo',backend)
    started=time.monotonic()
    try:
        with pytest.raises(HTTPFailure,match='controlled local backend failure'):
            fifo.post('/tokenize',{})
        assert time.monotonic()-started<5 and calls==['/tokenize']
        with pytest.raises(RuntimeError):fifo.post('/tokenize',{})
        assert calls==['/tokenize']
    finally:fifo.close()
    assert not (tmp_path/'fifo/model-request.fifo').exists()
