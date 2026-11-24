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

import fcntl
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
# Sent in the body of every request on the gateway route. It tells the gateway neither to answer from its store of
# earlier replies nor to store this one (ruling 37, point 9); without it the gateway returned a stored copy of an earlier
# reply to a byte-identical request. The direct Anthropic route does not send it.
GATEWAY_CACHE_BODY = {'no-cache': True, 'no-store': True}
GATEWAY_CACHE_NOTE = 'no-cache,no-store'    # what a usage row and a record of requested settings say about it
# The run's list of message ids, in the run root (ruling 44, point 3; ruling 45, point 1). One line for each reply the
# gateway route has accepted: its message id and the name of the block that got it. It holds no reply text and no outcome.
RUN_MESSAGE_IDS = 'message-ids.jsonl'
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


class RunMessageIds:
    """The file of message ids that every provider of one run reads and appends to. A block's own usage log holds only
    that block's replies, so a copy of a reply made in another block, or in an attempt that was set aside, would pass.
    This file sits in the run root, which is not moved when a block's folder is set aside, and is saved and restored
    with the run. Four blocks fly at once, each in its own process, so claim() takes a lock on the file for the
    read, the check and the append together."""

    def __init__(self, path: Path, block: str):
        self.path, self.block = Path(path), block

    def claim(self, message_id: str) -> bool:
        """True if the id was new and is now in the file. False if it was already there: the reply is a copy."""
        with open(self.path, 'a+b') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                data = f.read()
                for line in data.splitlines():
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue            # a line cut short by a crash; it never held a whole id
                    if isinstance(row, dict) and row.get('message_id') == message_id:
                        return False
                # A line cut short by a crash has no newline; start a new line so that the new row stays whole.
                lead = b'\n' if data and not data.endswith(b'\n') else b''
                f.write(lead + (json.dumps({'message_id': message_id, 'block': self.block}) + '\n').encode('utf-8'))
                f.flush()
                os.fsync(f.fileno())
                return True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)


class ClaudeProvider:
    name, reportable, relays = 'anthropic', False, False

    def __init__(self, usage_log: Path, model: str = DEFAULT_MODEL, effort: str | None = EFFORT,
                 max_output_tokens: int = MAX_OUTPUT_TOKENS, client=None, gem_model: str | None = None,
                 scored: bool = False, run_root: Path | None = None, block: str | None = None):
        if gem_model is None:
            spec = MODELS[model]
            self.client = client or anthropic.Anthropic(timeout=1800.0)
            self.model, self.prices, self.fallback, self.cache = spec['id'], spec['prices'], spec['fallback'], True
            self.via = 'anthropic'
        else:
            # Bedrock through LiteLLM: no server-side fallback, and caching is left off. List prices are only an
            # estimate here; the gateway's own charge is recorded as charged_usd, from the cost field of the stream's
            # last usage record, or from the response header when the reply was not streamed.
            family = next((k for k in MODELS if k in gem_model), None)
            self.client = client or gem_client()
            self.model, self.fallback, self.cache, self.via = gem_model, False, False, 'gem'
            self.prices = MODELS[family]['prices'] if family else None
        self.effort, self.max_output_tokens = effort, max_output_tokens
        # What the request body asks of the gateway's store of replies; None on the direct route, which sends nothing.
        self.gateway_cache = GATEWAY_CACHE_NOTE if self.via == 'gem' else None
        # Paper 3's scored runs (PROTOCOL.md) mark their exchanges reportable; everything else stays development.
        # Through Deakin's gateway there is no server-side fallback, and served_by is the gateway's model label.
        self.reportable = bool(scored)
        self.count_basis = 'api'
        self.usage_log = Path(usage_log)
        # On the gateway route with a run root, replies are also checked against every block of the run. With no run
        # root (the direct route, tools, scripted pilots) only this provider's own log is read, as before.
        self.run_ids = (RunMessageIds(Path(run_root) / RUN_MESSAGE_IDS, block or self.usage_log.parent.name)
                        if run_root is not None and self.via == 'gem' else None)
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

    def _seen_message_ids(self) -> set:
        """Every message id already in this provider's usage log. A row that does not parse is skipped here; the
        ledger's own readers are the ones that refuse it."""
        seen = set()
        if self.usage_log.exists():
            for line in self.usage_log.read_text(encoding='utf-8').splitlines():
                try:
                    mid = json.loads(line).get('message_id')
                except (ValueError, AttributeError):
                    continue
                if mid:
                    seen.add(mid)
        return seen

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
        if self.via == 'gem':
            options['extra_body'] = {'cache': dict(GATEWAY_CACHE_BODY)}
            row['gateway_cache'] = self.gateway_cache
        try:
            with self.client.beta.messages.stream(model=self.model, max_tokens=max_tokens, system=system,
                                                  messages=turns, **options) as stream:
                # The gateway puts its charge in the usage of the last message_delta event. The SDK keeps fields it
                # does not know in model_extra and does not copy them into the final message, so the events are read.
                charged_stream = None
                for event in (stream if hasattr(stream, '__iter__') else ()):
                    if getattr(event, 'type', None) == 'message_delta':
                        cost = (getattr(event.usage, 'model_extra', None) or {}).get('cost')
                        if cost is not None:
                            charged_stream = cost
                message = stream.get_final_message()
                api_request_id = getattr(stream, 'request_id', None)
                response = getattr(stream, 'response', None)
                charged_header = response.headers.get('x-litellm-response-cost') if response is not None else None
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
        charged = charged_stream if charged_stream is not None else (charged_header or None)
        charged = float(charged) if charged is not None else None
        # The run's file is claimed first, so the check and the append are one step. The own log is read as well.
        new_in_run = self.run_ids.claim(message.id) if self.run_ids is not None else True
        copied = (not new_in_run) or message.id in self._seen_message_ids()
        self._log({**row, 'status': 'copied' if copied else message.stop_reason, 'served_by': message.model,
                   'seconds': round(time.monotonic() - started, 1), 'input_tokens': usage.input_tokens,
                   'cache_write_tokens': usage.cache_creation_input_tokens,
                   'cache_read_tokens': usage.cache_read_input_tokens, 'output_tokens': usage.output_tokens,
                   'cost_usd': cost_usd(usage, self.prices) if self.prices else None,
                   'charged_usd': charged, **ids})
        if copied:
            # A message id is minted once per reply. One seen before is a stored copy of an earlier reply, not an
            # answer to this request (in this block or, by the run's file, in any block of the run), so it is passed on as a fault of the service and never as text.
            return ModelResponse('failed', None, tokens_in, usage.output_tokens, {**ids, 'error': 'RepeatedMessageId'})
        if message.stop_reason == 'max_tokens':
            return ModelResponse('cut_off', None, tokens_in, usage.output_tokens, ids)
        if message.stop_reason != 'end_turn' or not text:
            # A refusal the fallback model also declined, or an empty answer.
            return ModelResponse('failed', None, tokens_in, usage.output_tokens,
                                 {**ids, 'stop_reason': str(message.stop_reason)})
        return ModelResponse('answered', text, tokens_in, usage.output_tokens, ids)
