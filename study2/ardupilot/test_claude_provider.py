"""Offline checks of the Claude provider with a stand-in client: no network, no key, no cost.

Run from paper3/:  .venv/bin/python -m pytest ardupilot/test_claude_provider.py -q
"""
from contextlib import contextmanager
import json
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from telohelm.runtime.models import ModelRequest

from .claude_provider import MODELS, ClaudeProvider, cost_usd, to_api


def usage(i=100, w=0, r=0, o=50):
    return SimpleNamespace(input_tokens=i, cache_creation_input_tokens=w, cache_read_input_tokens=r, output_tokens=o)


class StandIn:
    """Records each request and returns a fixed message, or raises a fixed error."""
    def __init__(self, text='{"ok": true}', stop='end_turn', error=None):
        self.sent, self.text, self.stop, self.error = [], text, stop, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))
        self.messages = SimpleNamespace(count_tokens=lambda **kw: SimpleNamespace(input_tokens=1234))

    @contextmanager
    def _stream(self, **kwargs):
        self.sent.append(kwargs)
        if self.error is not None:
            raise self.error
        content = [SimpleNamespace(type='thinking', thinking=''), SimpleNamespace(type='text', text=self.text)]
        # Shaped like the SDK's streamed result: the request id is on the stream, not on the message.
        message = SimpleNamespace(content=content, usage=usage(), stop_reason=self.stop, id='msg_1',
                                  model=kwargs['model'])
        yield SimpleNamespace(get_final_message=lambda: message, request_id='req_1',
                              response=SimpleNamespace(headers={}))


def request(max_out=100_000):
    return ModelRequest('r1', 'a1', 'ep', 'cond', 'stream', 'reasoning_model',
                        (('system', 'rules'), ('user', 'task')), max_out, 1, 0, 0, 0.0)


def test_to_api_splits_system_from_turns():
    assert to_api((('system', 'a'), ('system', 'b'), ('user', 'u'), ('assistant', 'x'))) == (
        'a\n\nb', [{'role': 'user', 'content': 'u'}, {'role': 'assistant', 'content': 'x'}])
    with pytest.raises(ValueError):
        to_api((('user', 'u'), ('system', 'late')))
    with pytest.raises(ValueError):
        to_api((('tool', 't'),))


def test_cost_uses_each_token_class():
    prices = MODELS['opus']['prices']
    assert cost_usd(usage(i=1_000_000, w=0, r=0, o=0), prices) == 4.0
    assert cost_usd(usage(i=0, w=1_000_000, r=1_000_000, o=1_000_000), prices) == 5.0 + 0.2 + 20.0


def test_answer_is_returned_with_usage_and_logged(tmp_path):
    client = StandIn()
    provider = ClaudeProvider(tmp_path / 'u.jsonl', client=client)
    r = provider.complete(request())
    assert (r.status, r.text, r.tokens_in, r.tokens_out) == ('answered', '{"ok": true}', 100, 50)
    sent = client.sent[0]
    assert sent['model'] == 'claude-sonnet-5-5' and sent['max_tokens'] == 64_000 and sent['system'] == 'rules'
    assert sent['fallbacks'] == 'default' and sent['betas'] == ['server-side-fallback-2026-07-01']
    assert sent['output_config'] == {'effort': 'high'} and sent['cache_control'] == {'type': 'ephemeral'}
    row = json.loads((tmp_path / 'u.jsonl').read_text())
    assert row['status'] == 'end_turn' and row['cost_usd'] == cost_usd(usage(), MODELS['sonnet']['prices'])
    assert provider.count_tokens((('user', 'x'),)) == 1234


@pytest.mark.parametrize('stop, status', [('max_tokens', 'cut_off'), ('refusal', 'failed')])
def test_unusable_stops_pass_no_text(tmp_path, stop, status):
    r = ClaudeProvider(tmp_path / 'u.jsonl', client=StandIn(stop=stop)).complete(request())
    assert r.status == status and r.text is None


def test_api_errors_become_failed_or_timed_out(tmp_path):
    req = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')
    failed = anthropic.APIConnectionError(request=req)
    timed = anthropic.APITimeoutError(request=req)
    assert ClaudeProvider(tmp_path / 'a.jsonl', client=StandIn(error=failed)).complete(request()).status == 'failed'
    assert ClaudeProvider(tmp_path / 'b.jsonl', client=StandIn(error=timed)).complete(request()).status == 'timed_out'


def test_haiku_is_sent_without_the_fallback_it_does_not_have(tmp_path):
    client = StandIn()
    ClaudeProvider(tmp_path / 'u.jsonl', model='haiku', client=client).complete(request())
    assert client.sent[0]['model'] == 'claude-haiku-5-5'
    assert 'fallbacks' not in client.sent[0] and 'betas' not in client.sent[0]


def test_gem_route_sends_no_anthropic_only_options(tmp_path, monkeypatch):
    client = StandIn()
    provider = ClaudeProvider(tmp_path / 'u.jsonl', client=client, gem_model='bedrock/au.anthropic.claude-sonnet-5')
    provider.complete(request())
    sent = client.sent[0]
    assert sent['model'] == 'bedrock/au.anthropic.claude-sonnet-5'
    assert not {'fallbacks', 'betas', 'cache_control'} & set(sent) and sent['output_config'] == {'effort': 'high'}
    row = json.loads((tmp_path / 'u.jsonl').read_text())
    assert row['via'] == 'gem' and row['cost_usd'] == cost_usd(usage(), MODELS['sonnet']['prices'])


def test_gem_needs_its_own_variables(monkeypatch, tmp_path):
    from .claude_provider import gem_client
    monkeypatch.delenv('GEM_BASE_URL', raising=False)
    monkeypatch.delenv('GEM_API_KEY', raising=False)
    with pytest.raises(RuntimeError):
        gem_client(path=tmp_path / 'missing.env')


def test_gem_settings_file_must_be_private(monkeypatch, tmp_path):
    from .claude_provider import gem_settings
    monkeypatch.delenv('GEM_BASE_URL', raising=False)
    monkeypatch.delenv('GEM_API_KEY', raising=False)
    f = tmp_path / 'gem.env'
    f.write_text('export GEM_BASE_URL=https://gateway.test\nGEM_API_KEY="sk-test-not-a-real-key"\n')
    f.chmod(0o644)
    with pytest.raises(RuntimeError):
        gem_settings(f)
    f.chmod(0o600)
    assert gem_settings(f) == {'GEM_BASE_URL': 'https://gateway.test', 'GEM_API_KEY': 'sk-test-not-a-real-key'}


def test_redact_removes_key_shapes():
    from .claude_provider import redact
    assert 'abcdef123' not in redact('bad key sk-abcdef1234567 for user')
