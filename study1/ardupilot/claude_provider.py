"""Claude as Telohelm's learning model, for development runs only.

Maps Telohelm's (speaker, text) messages onto Anthropic's Messages API, streams the reply and records what each call
used and cost. reportable is False, so the gateway marks every record it makes unreportable: these runs speed up
development and are not evidence. Paper 3's frozen runs use the same local model as paper 2.

Two routes. Directly to Anthropic, with credentials from the environment as the SDK finds them. Or through Deakin's
GEM gateway (LiteLLM in front of Amazon Bedrock in Australia), with the address and key in GEM_BASE_URL and
GEM_API_KEY. Those names are deliberately not ANTHROPIC_*, which Claude Code also reads. This module never writes or
prints a key.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import time

import anthropic

from telohelm.runtime.models import ModelRequest, ModelResponse

EFFORT = 'high'
MAX_OUTPUT_TOKENS = 64_000
# US dollars per million tokens (Anthropic list prices, checked 30 October 2026; Haiku's up to 100K input tokens).
# A cache write costs 1.25 times the input price at the default five-minute lifetime and a cache read 0.1 times;
# Haiku's cache prices are worked out from those multipliers, not read from the price list.
# fallback: whether a refusal is re-run server-side on Anthropic's recommended model (Haiku has no such fallback).
MODELS = {
    'sonnet': dict(id='claude-sonnet-5-5', fallback=True,
                   prices={'input': 2.00, 'cache_write': 2.50, 'cache_read': 0.20, 'output': 10.00}),
    'haiku': dict(id='claude-haiku-5-5', fallback=False,
                  prices={'input': 0.10, 'cache_write': 0.125, 'cache_read': 0.01, 'output': 0.50}),
    'opus': dict(id='claude-opus-5-5', fallback=True,
                 prices={'input': 4.00, 'cache_write': 5.00, 'cache_read': 0.20, 'output': 20.00}),
}
DEFAULT_MODEL = 'sonnet'
FALLBACK_BETAS = ['server-side-fallback-2026-07-01']
GEM_ENV = ('GEM_BASE_URL', 'GEM_API_KEY')
GEM_FILE = Path.home() / '.config' / 'telohelm' / 'gem.env'


def gem_settings(path: Path = GEM_FILE) -> dict:
    """GEM_BASE_URL and GEM_API_KEY from the environment, or else from a KEY=VALUE file only its owner can read."""
    found = {name: os.environ.get(name) for name in GEM_ENV}
    if all(found.values()):
        return found
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise RuntimeError(f'{path} can be read by others; run: chmod 600 {path}')
        for line in path.read_text().splitlines():
            name, sep, value = line.strip().removeprefix('export ').partition('=')
            if sep and name.strip() in GEM_ENV and not found[name.strip()]:
                found[name.strip()] = value.strip().strip('"').strip("'")
    if not all(found.values()):
        raise RuntimeError(f'Set GEM_BASE_URL and GEM_API_KEY in the environment or in {path}')
    return found


def gem_client(timeout: float = 1800.0, path: Path = GEM_FILE):
    settings = gem_settings(path)
    return anthropic.Anthropic(base_url=settings['GEM_BASE_URL'], auth_token=settings['GEM_API_KEY'], timeout=timeout)


def redact(text) -> str:
    """Gateway error text with anything shaped like a key removed."""
    return re.sub(r'sk-[A-Za-z0-9_\-]{6,}', 'sk-<redacted>', str(text))


def to_api(messages):
    """Telohelm's ((speaker, text), ...) as a system prompt and a list of user and assistant turns."""
    system, turns = [], []
    for speaker, text in messages:
        if speaker == 'system':
            if turns:
                raise ValueError('a system message after the conversation has started')
            system.append(text)
        elif speaker in ('user', 'assistant'):
            turns.append({'role': speaker, 'content': text})
        else:
            raise ValueError(f'unknown speaker {speaker!r}')
    return '\n\n'.join(system), turns


def cost_usd(usage, prices) -> float:
    return round(((usage.input_tokens or 0) * prices['input']
                  + (usage.cache_creation_input_tokens or 0) * prices['cache_write']
                  + (usage.cache_read_input_tokens or 0) * prices['cache_read']
                  + (usage.output_tokens or 0) * prices['output']) / 1e6, 6)


class ClaudeProvider:
    name, reportable, relays = 'anthropic', False, False

    def __init__(self, usage_log: Path, model: str = DEFAULT_MODEL, effort: str | None = EFFORT,
                 max_output_tokens: int = MAX_OUTPUT_TOKENS, client=None, gem_model: str | None = None,
                 scored: bool = False):
        if gem_model is None:
            spec = MODELS[model]
            self.client = client or anthropic.Anthropic(timeout=1800.0)
            self.model, self.prices, self.fallback, self.cache = spec['id'], spec['prices'], spec['fallback'], True
            self.via = 'anthropic'
        else:
            # Bedrock through LiteLLM: no server-side fallback, and caching is left off. List prices are only an
            # estimate here; the gateway's own charge is recorded from its response header.
            family = next((k for k in MODELS if k in gem_model), None)
            self.client = client or gem_client()
            self.model, self.fallback, self.cache, self.via = gem_model, False, False, 'gem'
            self.prices = MODELS[family]['prices'] if family else None
        self.effort, self.max_output_tokens = effort, max_output_tokens
        # Paper 3's scored runs (PROTOCOL.md) mark their exchanges reportable; everything else stays development.
        # Through Deakin's gateway there is no server-side fallback, and served_by is the gateway's model label.
        self.reportable = bool(scored)
        self.count_basis = 'api'
        self.usage_log = Path(usage_log)
        self.calls = 0

    def count_tokens(self, messages) -> int:
        """Input tokens as Anthropic counts them, for Telohelm's preflight cap."""
        system, turns = to_api(messages)
        try:
            return self.client.messages.count_tokens(model=self.model, system=system, messages=turns).input_tokens
        except anthropic.APIStatusError:
            if self.via != 'gem':
                raise
        # The gateway may not offer counting. Three characters a token overstates English text and code, so the
        # preflight cap stays on the safe side.
        self.count_basis = 'estimate'
        return math.ceil((len(system) + sum(len(t['content']) for t in turns)) / 3)

    def _log(self, row):
        with open(self.usage_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row) + '\n')

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        system, turns = to_api(request.messages)
        max_tokens = min(request.max_output_tokens, self.max_output_tokens)
        started = time.monotonic()
        row = {'request_id': request.request_id, 'via': self.via, 'model': self.model, 'effort': self.effort,
               'max_tokens': max_tokens, 'token_count_basis': self.count_basis}
        options = {}
        if self.effort is not None:
            options['output_config'] = {'effort': self.effort}
        if self.cache:
            options['cache_control'] = {'type': 'ephemeral'}
        if self.fallback:
            options.update(betas=FALLBACK_BETAS, fallbacks='default')
        try:
            with self.client.beta.messages.stream(model=self.model, max_tokens=max_tokens, system=system,
                                                  messages=turns, **options) as stream:
                message = stream.get_final_message()
                api_request_id = getattr(stream, 'request_id', None)
                response = getattr(stream, 'response', None)
                charged = response.headers.get('x-litellm-response-cost') if response is not None else None
        except anthropic.APITimeoutError:
            self._log({**row, 'status': 'timed_out', 'seconds': round(time.monotonic() - started, 1)})
            return ModelResponse('timed_out')
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            self._log({**row, 'status': 'failed', 'error': type(exc).__name__,
                       'http_status': getattr(exc, 'status_code', None), 'detail': redact(exc)[:300],
                       'seconds': round(time.monotonic() - started, 1)})
            return ModelResponse('failed', provider_ids={'error': type(exc).__name__})
        usage = message.usage
        text = ''.join(block.text for block in message.content if block.type == 'text')
        tokens_in = ((usage.input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
                     + (usage.cache_read_input_tokens or 0))
        ids = {'message_id': message.id, 'api_request_id': api_request_id, 'served_by': message.model}
        self._log({**row, 'status': message.stop_reason, 'served_by': message.model,
                   'seconds': round(time.monotonic() - started, 1), 'input_tokens': usage.input_tokens,
                   'cache_write_tokens': usage.cache_creation_input_tokens,
                   'cache_read_tokens': usage.cache_read_input_tokens, 'output_tokens': usage.output_tokens,
                   'cost_usd': cost_usd(usage, self.prices) if self.prices else None,
                   'charged_usd': float(charged) if charged else None, **ids})
        if message.stop_reason == 'max_tokens':
            return ModelResponse('cut_off', None, tokens_in, usage.output_tokens, ids)
        if message.stop_reason != 'end_turn' or not text:
            # A refusal the fallback model also declined, or an empty answer.
            return ModelResponse('failed', None, tokens_in, usage.output_tokens,
                                 {**ids, 'stop_reason': str(message.stop_reason)})
        return ModelResponse('answered', text, tokens_in, usage.output_tokens, ids)
