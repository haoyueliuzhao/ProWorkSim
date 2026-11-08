"""Use the task process's kernel network namespace, never a mounted sysfs view."""
import builtins
import io
import json
import os
import socket

import pytest
from proworksim.software_benchmark_requests1724_v160 import RELAY_INTERPRETER_PROBE


def test_namespace_interface_probe_ignores_foreign_sysfs_view(monkeypatch,capsys):
    reads=[]
    original=builtins.open
    def open_file(path,*a,**kw):
        reads.append(path)
        if path=='/proc/self/net/route':return io.StringIO('Iface\tDestination\tGateway\n')
        return original(path,*a,**kw)
    def sysfs_view(path):
        if path=='/sys/class/net':raise AssertionError('Mounted sysfs must not decide this namespace boundary')
        return []
    monkeypatch.setattr(builtins,'open',open_file)
    monkeypatch.setattr(os,'listdir',sysfs_view)
    monkeypatch.setattr(socket,'if_nameindex',lambda:[(1,'lo')])
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a:[(None,None,None,None,('127.0.0.1',80))])
    exec(compile(RELAY_INTERPRETER_PROBE,'cpu-current-netns-probe','exec'),{})
    result=json.loads(capsys.readouterr().out)
    assert result['interfaces']==['lo'] and result['gateway_present'] is False
    assert result['interfaces_source']=='socket.if_nameindex'
    assert reads==['/proc/self/net/route']
    assert result['routes_source']=='/proc/self/net/route'


@pytest.mark.parametrize('interfaces,route',[
    ([(1,'lo'),(2,'foreign0')],'Iface\tDestination\tGateway\n'),
    ([(1,'lo')],'Iface\tDestination\tGateway\nlo\t00000000\t0100007F\n'),
])
def test_real_namespace_extra_interface_or_gateway_is_rejected(monkeypatch,interfaces,route):
    monkeypatch.setattr(socket,'if_nameindex',lambda:interfaces)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a:[(None,None,None,None,('127.0.0.1',80))])
    monkeypatch.setattr(builtins,'open',lambda path,*a,**kw:io.StringIO(route))
    with pytest.raises(RuntimeError):
        exec(compile(RELAY_INTERPRETER_PROBE,'cpu-rejected-netns-probe','exec'),{})
