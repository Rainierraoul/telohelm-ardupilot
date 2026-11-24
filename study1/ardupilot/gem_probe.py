"""Check what the Deakin GEM gateway offers this key, without printing the key.

Run from paper3/:  .venv/bin/python -m ardupilot.gem_probe [MODEL ...]
With no models named, it tries up to six Claude models the key can see. Each test is one short message, a fraction
of a cent; the charges the gateway reports are printed.
"""
import sys

import anthropic

from .claude_provider import gem_client, redact

ASK = [{'role': 'user', 'content': 'Reply with the single word OK.'}]


def main(argv):
    client = gem_client(timeout=120.0)
    listing = client.get('/v1/models', cast_to=object)
    ids = sorted(m['id'] for m in listing.get('data', [])) if isinstance(listing, dict) else []
    print('Models visible to this key:')
    for i in ids:
        print('  ', i)
    targets = argv or [i for i in ids if 'claude' in i][:6]
    for model in targets:
        for label, extra in (('plain', {}), ('effort high', {'output_config': {'effort': 'high'}})):
            try:
                with client.messages.stream(model=model, max_tokens=2000, messages=ASK, **extra) as stream:
                    message = stream.get_final_message()
                    charged = stream.response.headers.get('x-litellm-response-cost')
                text = ''.join(b.text for b in message.content if b.type == 'text').strip()
                print(f'{model} | {label}: ok, stop {message.stop_reason}, said {text[:20]!r}, served by '
                      f'{message.model}, tokens {message.usage.input_tokens}/{message.usage.output_tokens}, '
                      f'charged {charged}')
            except anthropic.APIStatusError as exc:
                print(f'{model} | {label}: HTTP {exc.status_code}: {redact(exc.message)[:200]}')
            except anthropic.APIConnectionError as exc:
                print(f'{model} | {label}: no connection ({type(exc).__name__})')
        try:
            n = client.messages.count_tokens(model=model, messages=ASK).input_tokens
            print(f'{model} | token counting: ok ({n})')
        except anthropic.APIStatusError as exc:
            print(f'{model} | token counting: HTTP {exc.status_code}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
