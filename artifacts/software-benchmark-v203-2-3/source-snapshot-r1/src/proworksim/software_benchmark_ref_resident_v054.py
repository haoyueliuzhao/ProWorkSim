"""Session fencing for a persistent, unchanged vLLM REF numerical service.

Only control-plane state persists between episodes. Chat request bodies pass
unchanged to the official API. This module adds no training or model method.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import time

ROOT = Path('/data0/zhuxinrui/projects/ProWorkSim')
VERSION = 'v054-persistent-ref-session-v1'
SLOTS_SHA = '55899d0b83a5bab1082bccb50496fb6c1d7111ecb951fc4d61c222be19d88676'
MAX_BODY = 16 * 1024**2


def checked(item):
    path = Path(item['path'])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != item['sha256'] or len(raw) != item['bytes']:
        raise ValueError('Pinned resident/session evidence changed')
    return json.loads(raw)


def atomic(path, body):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.writing')
    with temporary.open('w') as stream:
        json.dump(body, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def identity(pid):
    raw = Path('/proc/' + str(int(pid)) + '/stat').read_text()
    return {'pid': int(pid), 'start_ticks': int(raw[raw.rfind(')') + 2:].split()[19])}


def alive(expected):
    try:
        return identity(expected['pid']) == expected
    except (OSError, ValueError):
        return False


def verify_claim(arguments, *, require_entered=False):
    slot, claim_id = arguments['slot'], arguments['claim_id']
    if slot.get('arm') != 'REF' or not re.fullmatch(r'[0-9a-f]{32}', claim_id):
        raise ValueError('Only a preclaimed REF slot is accepted')
    slot_file = ROOT / 'artifacts/software-benchmark-v054/manifests/slots.json'
    raw = slot_file.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SLOTS_SHA:
        raise ValueError('Frozen slot panel changed')
    if slot not in json.loads(raw)['slots']:
        raise ValueError('Slot identity or seed changed')
    permit = checked(arguments['authorization'])
    if (permit.get('execution_authorized') is not True or permit.get('slots_sha256') != SLOTS_SHA
            or slot['slot_id'] not in permit.get('slot_ids', [])):
        raise ValueError('This slot has no formal authorization')
    claim_path = ROOT / 'runs/software-benchmark-v054/episode-claims' / hashlib.sha256(slot['slot_id'].encode()).hexdigest() / 'claim.json'
    if claim_path.exists():
        claim = json.loads(claim_path.read_bytes())
        if (claim['claim_id'] != claim_id or claim['slot'] != slot
                or claim['authorization'] != arguments['authorization']):
            raise ValueError('Resident session differs from the global once-only claim')
    elif require_entered:
        raise ValueError('Inference requires the global once-only slot claim')
    if require_entered:
        entered = json.loads((claim_path.parent / 'entered.json').read_bytes())
        if entered['claim_id'] != claim_id or entered['slot'] != slot:
            raise ValueError('Inference requires the exact entered episode')
    if not alive(arguments['host_process']):
        raise ValueError('The episode session sentinel is not alive')


class RefSessionGate:
    """Official --middleware ASGI hook, with no arbitrary RPC or dev routes."""
    def __init__(self, app):
        self.app = app
        raw = Path(os.environ['PWS_REF_RESIDENT_SPEC']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != os.environ['PWS_REF_RESIDENT_SPEC_SHA256']:
            raise ValueError('Resident specification changed before ASGI initialization')
        self.spec = json.loads(raw)
        self.root = Path(self.spec['root'])
        self.key = Path(self.spec['api_key_file']).read_text().strip()
        if len(self.key) < 32:
            raise ValueError('Missing private resident API authentication')
        if (self.root / 'session-state.json').exists():
            raise ValueError('Resident state may not be silently restarted or reused')
        self.phase, self.active, self.inflight = 'idle', None, 0
        self.guard = asyncio.Lock()
        self.engine = None
        self.watchdog = None
        self.completed = 0
        self.preparation_slots = set()
        self.preparation_calls = []
        self.preparation_completed = 0
        self.save()

    def save(self):
        atomic(self.root / 'session-state.json', {
            'version': VERSION, 'phase': self.phase, 'inflight_http': self.inflight,
            'active_claim': self.active['claim_id'] if self.active else None,
            'active_slot': self.active['slot']['slot_id'] if self.active else None,
            'completed_sessions': self.completed, 'api_pid': os.getpid(),
            'preparation_completed_sessions': self.preparation_completed,
            'preparation_generation_calls': len(self.preparation_calls),
            'preparation_calls': self.preparation_calls,
            'prefix_caching': False, 'weights_unloaded_between_sessions': False})

    def preparation(self, arguments):
        reference = self.spec.get('preparation_permit')
        if reference is None or arguments.get('authorization') != reference:
            raise ValueError('This resident has no matching independent preparation permit')
        permit = checked(reference)
        if (permit.get('version') != 'v054-ref-resident-two-session-preparation-v1'
                or permit.get('model_execution_authorized') is not True
                or permit.get('formal_execution_authorized') is not False
                or permit.get('maximum_generation_calls') != 2
                or permit.get('maximum_calls_per_session') != 1
                or permit.get('maximum_input_tokens') != 8192
                or permit.get('model_manifest') != self.spec['model_manifest']
                or len(permit.get('sessions', [])) != 2
                or len({row['slot']['seed'] for row in permit['sessions']}) != 2):
            raise ValueError('Preparation permit differs from the bounded two-session diagnostic')
        slot = arguments['slot']
        rows = [row for row in permit['sessions'] if row['slot'] == slot]
        if (len(rows) != 1 or slot.get('arm') != 'REF'
                or not slot.get('slot_id', '').startswith('synthetic-v054-ref-resident-')
                or not re.fullmatch(r'[0-9a-f]{32}', arguments['claim_id'])
                or slot['slot_id'] in self.preparation_slots or len(self.preparation_calls) >= 2
                or not alive(arguments['host_process'])):
            raise ValueError('Preparation session is unknown, repeated or stale')
        request = checked(rows[0]['request'])
        if request.get('seed') != slot['seed'] or request.get('max_tokens') != 32768:
            raise ValueError('Preparation retains the original output cap and independent declared seed')
        return request

    async def reply(self, send, status, body):
        raw = json.dumps(body).encode()
        await send({'type': 'http.response.start', 'status': status,
                    'headers': [(b'content-type', b'application/json'),
                                (b'content-length', str(len(raw)).encode())]})
        await send({'type': 'http.response.body', 'body': raw})

    async def body(self, receive):
        data = bytearray()
        while True:
            item = await receive()
            if item['type'] != 'http.request':
                raise ValueError('Incomplete request body')
            data.extend(item.get('body', b''))
            if len(data) > MAX_BODY:
                raise ValueError('Complete request exceeds the finite bound')
            if not item.get('more_body', False):
                return bytes(data)

    async def drain(self, *, abort=False):
        # vLLM 0.32.0 implements pause/wait in the engine scheduler and clears
        # KV/prefix blocks without sleep(), empty_cache(), or unloading weights.
        await asyncio.wait_for(self.engine.pause_generation(
            mode='abort' if abort else 'wait', clear_cache=True), timeout=30)
        until = time.monotonic() + 5
        while self.engine.get_num_unfinished_requests() and time.monotonic() < until:
            await asyncio.sleep(.02)
        if self.engine.get_num_unfinished_requests() != 0 or not await self.engine.is_paused():
            raise RuntimeError('Engine did not become paused and empty')
        if not await self.engine.reset_prefix_cache(False, False):
            raise RuntimeError('Engine still retains referenced KV/prefix blocks')
        return {'engine_unfinished': 0, 'engine_paused': True, 'cache_reset': True,
                'weights_unloaded': False}

    async def poison(self, reason):
        async with self.guard:
            self.phase = 'poisoned'
            self.save()
            proof = {'reason': reason, 'actual_usage_unknown': True, 'automatic_replay': False}
            try:
                proof.update(await self.drain(abort=True))
            except Exception as error:
                proof.update(drain_failed=type(error).__name__ + ': ' + str(error))
            if self.active:
                atomic(self.root / 'sessions' / self.active['claim_id'] / 'poison.json', proof)
            self.save()
            return {'poisoned': True, **proof}

    async def watch_owner(self):
        while True:
            await asyncio.sleep(.2)
            if self.phase == 'active' and self.active and not alive(self.active['host_process']):
                await self.poison('episode_sentinel_exited_without_normal_release')

    async def control(self, operation, arguments):
        if operation == 'status':
            return {'version': VERSION, 'phase': self.phase, 'state': self.phase,
                    'poisoned': self.phase == 'poisoned', 'inflight': self.inflight,
                    'inflight_http': self.inflight,
                    'active_claim': self.active['claim_id'] if self.active else None,
                    'completed_sessions': self.completed, 'resident_pid': os.getpid(),
                    'preparation_generation_calls': len(self.preparation_calls),
                    'preparation_completed_sessions': self.preparation_completed}
        if operation == 'release':
            return await self.release(arguments)
        if operation == 'poison':
            if not self.active or arguments.get('claim_id') != self.active['claim_id']:
                raise ValueError('A different claim cannot poison this resident session')
            return await self.poison('explicit_host_failure')
        async with self.guard:
            if operation in {'acquire', 'acquire_preparation'}:
                if self.phase == 'poisoned':
                    raise ValueError('Poisoned resident requires explicit fault review')
                if self.phase != 'idle' or self.inflight:
                    return {'state': 'busy', 'active_claim': self.active['claim_id'] if self.active else None}
                preparation_only = operation == 'acquire_preparation'
                if preparation_only:
                    fixed_request = self.preparation(arguments)
                else:
                    if self.spec.get('preparation_permit') and self.preparation_completed != 2:
                        raise ValueError('The resident two-session preparation has not completed')
                    verify_claim(arguments)
                directory = self.root / 'sessions' / arguments['claim_id']
                directory.mkdir(parents=True, exist_ok=False)
                try:
                    proof = await self.drain()
                    self.active = {**arguments, 'token': secrets.token_urlsafe(48),
                                   'preparation_only': preparation_only}
                    if preparation_only:
                        self.preparation_slots.add(arguments['slot']['slot_id'])
                        self.active.update(preparation_request=fixed_request,
                                           preparation_call_started=False, preparation_count=None)
                    self.phase = 'active'
                    atomic(directory / 'acquire.json', {
                        'version': VERSION, 'slot': arguments['slot'], 'claim_id': arguments['claim_id'],
                        'host_process': arguments['host_process'], 'empty_initial_engine': proof,
                        'preparation_only': preparation_only,
                        'new_client_ledger_required': True, 'no_history_or_feedback_inherited': True})
                    await self.engine.resume_generation()
                    self.save()
                except BaseException:
                    self.phase = 'poisoned'
                    self.save()
                    raise
                value = json.loads((self.root / 'identity.json').read_bytes())
                value.update(resident_session={'version': VERSION, 'claim_id': arguments['claim_id'],
                                              'slot_id': arguments['slot']['slot_id']})
                return {'claim_id': arguments['claim_id'], 'identity': value,
                        'ref_endpoint': 'http://127.0.0.1:18054',
                        'ref_session_token': self.active['token'], 'acquired': True, 'state': 'acquired'}
            raise ValueError('Unknown resident control operation')

    async def release(self, arguments):
        async with self.guard:
            if (self.phase != 'active' or not self.active
                    or arguments.get('claim_id') != self.active['claim_id']
                    or not hmac.compare_digest(arguments.get('session_token', ''), self.active['token'])):
                raise ValueError('Only this completed session can release an idle engine')
            self.phase = 'closing'
            self.save()
        try:
            until = time.monotonic() + 5
            while self.inflight and time.monotonic() < until:
                await asyncio.sleep(.01)
            if self.inflight:
                raise RuntimeError('HTTP request did not finish before normal release')
            async with self.guard:
                if self.phase != 'closing':
                    raise ValueError('Session became poisoned while releasing')
                proof = await self.drain()
                receipt = {'version': VERSION, 'claim_id': self.active['claim_id'],
                           'released': True, 'quiescent': True, 'resident_still_loaded': True, **proof}
                if self.active.get('preparation_only'):
                    calls = [row for row in self.preparation_calls if row['claim_id'] == self.active['claim_id']]
                    if len(calls) != 1 or calls[0]['status'] != 'settled':
                        raise ValueError('A preparation session requires exactly one completely accounted call')
                    self.preparation_completed += 1
                    receipt.update(preparation_only=True, actual_usage=calls[0]['usage'])
                atomic(self.root / 'sessions' / self.active['claim_id'] / 'release.json', receipt)
                self.active, self.phase = None, 'idle'
                self.completed += 1
                self.save()
                return receipt
        except BaseException:
            self.phase = 'poisoned'
            self.save()
            raise

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = {key.lower(): value.decode() for key, value in scope.get('headers', [])}
        authorized = hmac.compare_digest(headers.get(b'authorization', ''), 'Bearer ' + self.key)
        if not authorized:
            return await self.reply(send, 401, {'error': 'Private resident authentication required'})
        if self.engine is None:
            self.engine = scope['app'].state.engine_client
            if self.engine.vllm_config.cache_config.enable_prefix_caching is not False:
                raise ValueError('Persistent REF must retain disabled prefix caching')
            self.watchdog = asyncio.create_task(self.watch_owner())
        path = scope['path']
        if path.startswith('/pws/ref/'):
            try:
                if scope['method'] != 'POST':
                    raise ValueError('Control operations require POST')
                arguments = json.loads(await self.body(receive))
                result = await self.control(path.rsplit('/', 1)[-1], arguments)
                return await self.reply(send, 200, result)
            except Exception as error:
                return await self.reply(send, 409, {'error': type(error).__name__ + ': ' + str(error)})
        if path in {'/v1/models', '/health'} and scope['method'] == 'GET':
            return await self.app(scope, receive, send)
        if path not in {'/tokenize', '/v1/chat/completions'} or scope['method'] != 'POST':
            return await self.reply(send, 403, {'error': 'Only the fixed stateless REF API is enabled'})
        raw = await self.body(receive)
        async with self.guard:
            if (self.phase != 'active' or self.active is None or self.inflight
                    or not hmac.compare_digest(headers.get(b'x-pws-ref-session', ''), self.active['token'])
                    or not alive(self.active['host_process'])):
                return await self.reply(send, 409, {'error': 'Inactive, stale or overlapping episode session'})
            preparation_only = self.active.get('preparation_only', False)
            if preparation_only:
                expected = self.active['preparation_request']
                if path == '/tokenize':
                    expected = {key: expected[key] for key in (
                        'model', 'messages', 'tools', 'chat_template_kwargs', 'add_generation_prompt',
                        'continue_final_message', 'add_special_tokens')}
                if json.loads(raw) != expected:
                    return await self.reply(send, 409, {'error': 'Only the exact predeclared synthetic request is authorized'})
                if path == '/v1/chat/completions':
                    count = self.active['preparation_count']
                    if (self.active['preparation_call_started'] or len(self.preparation_calls) >= 2
                            or type(count) is not int or not 0 < count <= 8192):
                        return await self.reply(send, 409, {'error': 'Preparation call limit or exact count gate'})
                    self.active['preparation_call_started'] = True
                    self.preparation_calls.append({'claim_id': self.active['claim_id'],
                        'slot_id': self.active['slot']['slot_id'], 'seed': self.active['slot']['seed'],
                        'prompt_tokens': count, 'reserved_tokens': count + 32768,
                        'status': 'dispatched_usage_unknown', 'usage': None})
            else:
                try:
                    verify_claim(self.active, require_entered=True)
                except (OSError, ValueError, KeyError) as error:
                    return await self.reply(send, 409, {'error': str(error)})
            if path == '/v1/chat/completions':
                request = json.loads(raw)
                if request.get('seed') != self.active['slot']['seed'] or request.get('stream') is not False:
                    return await self.reply(send, 409, {'error': 'Predeclared seed and non-streaming request required'})
            self.inflight = 1
            self.save()
        delivered, status, complete, successful = False, None, False, False
        captured = bytearray()
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': raw, 'more_body': False}
            return await receive()
        async def observe(message):
            nonlocal status, complete
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)
            if preparation_only and message['type'] == 'http.response.body':
                captured.extend(message.get('body', b''))
                if len(captured) > MAX_BODY:
                    raise ValueError('Complete preparation response exceeds the explicit bound')
            if message['type'] == 'http.response.body' and not message.get('more_body', False):
                complete = True
        try:
            await self.app(scope, replay, observe)
            if preparation_only and status == 200 and complete:
                body = json.loads(captured)
                if path == '/tokenize':
                    if (body.get('count') != len(body.get('tokens', []))
                            or type(body.get('count')) is not int or not 0 < body['count'] <= 8192
                            or body.get('max_model_len') != 131072):
                        raise ValueError('Preparation exact tokenizer/window gate failed')
                    self.active['preparation_count'] = body['count']
                else:
                    usage = body.get('usage', {})
                    call = self.preparation_calls[-1]
                    if (any(type(usage.get(key)) is not int for key in
                            ('prompt_tokens', 'completion_tokens', 'total_tokens'))
                            or usage['prompt_tokens'] != call['prompt_tokens']
                            or not 0 < usage['completion_tokens'] <= 32768
                            or usage['total_tokens'] != usage['prompt_tokens'] + usage['completion_tokens']):
                        raise ValueError('Preparation usage is uncertain; never replay')
                    call.update(status='settled', usage=usage)
            successful = status == 200 and complete
        finally:
            async with self.guard:
                self.inflight = 0
                if not successful:
                    self.phase = 'poisoned'
                self.save()
            if not successful:
                await self.poison('incomplete_or_failed_official_http_response')


class RefResidentClient:
    def __init__(self, endpoint, api_key_file, timeout_seconds=45):
        if endpoint != 'http://127.0.0.1:18054':
            raise ValueError('Only the fixed local REF resident is supported')
        self.key = Path(api_key_file).read_text().strip()
        self.timeout_seconds = timeout_seconds

    def call(self, operation, **arguments):
        if operation not in {'acquire', 'acquire_preparation', 'release', 'status', 'poison'}:
            raise ValueError('Unapproved resident control operation')
        connection = http.client.HTTPConnection('127.0.0.1', 18054, timeout=self.timeout_seconds)
        try:
            connection.request('POST', '/pws/ref/' + operation, body=json.dumps(arguments),
                               headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read(MAX_BODY + 1)
            if response.status != 200 or len(raw) > MAX_BODY:
                raise RuntimeError('Resident control failed; no automatic retry: HTTP ' + str(response.status))
            return json.loads(raw)
        finally:
            connection.close()


class SessionAuthenticatedLoopbackHTTP:
    """Same exact transport, with an additional claim-fenced session header."""
    def __init__(self, endpoint, key_file, session_token, *, timeout_seconds=1800,
                 max_response_bytes=MAX_BODY):
        from .software_benchmark_ref_deployment_v054 import AuthenticatedLoopbackHTTP
        self.base = AuthenticatedLoopbackHTTP(endpoint, key_file, timeout_seconds=timeout_seconds,
                                               max_response_bytes=max_response_bytes)
        self.session_token = session_token
        self.port = self.base.port

    def post(self, path, payload):
        from .software_benchmark_exact_transport_v054 import HTTPFailure
        from .storage import json_bytes
        if path not in {'/tokenize', '/v1/chat/completions'}:
            raise ValueError('Unapproved episode inference operation')
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=self.base.timeout_seconds)
        status, raw = None, None
        try:
            connection.request('POST', path, body=json_bytes(payload), headers={
                'Authorization': 'Bearer ' + self.base.key, 'X-PWS-REF-Session': self.session_token,
                'Content-Type': 'application/json'})
            response = connection.getresponse()
            status = response.status
            body = response.read(self.base.max_response_bytes + 1)
            if len(body) > self.base.max_response_bytes:
                raise HTTPFailure('Response exceeds complete-response bound', status=status)
            raw = body.decode('utf-8')
            if status != 200:
                raise HTTPFailure('Non-200; no redirect or retry', status=status, raw_body=raw)
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('Expected complete response object')
            return result
        except HTTPFailure:
            raise
        except Exception as error:
            raise HTTPFailure(str(error), status=status, raw_body=raw) from error
        finally:
            connection.close()
