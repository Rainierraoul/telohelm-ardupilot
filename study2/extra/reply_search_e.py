"""Search arm E's replies for any remark that the earlier attempt's code was missing (Online Resource 1, S19.8).

    python3 -I extra/reply_search_e.py EXTRA_SAVED TAG

EXTRA_SAVED holds extra-TAG-<task>/runs/extra-TAG-<task>/. Arm E's requests kept the rules text, which says that the
latest attempt's source is included, while the source was left out. This reads the text of every reply arm E drew
(candidates rE1 and rE2 of every learnE block) and prints each match of the pattern below with the text around it,
then the number of replies read and of matches. Written after the run, as a check; it reads the records and writes
nothing. On 23 November 2026 it read 187 replies and found no match.
"""
import json
import re
import sys
from pathlib import Path

PATTERN = re.compile(r"not (shown|included|provided|given|visible|available)|wasn'?t (shown|included|provided|given)|"
                     r"(cannot|can'?t|unable to) see|without (seeing|the source|its source|access)|"
                     r"no (source|code) (was|is)? ?(shown|given|provided|available)|"
                     r"source (is|was|not) (missing|absent|omitted)|missing (source|code)|omitted", re.I)


def main(saved: Path, tag: str) -> None:
    replies = matches = 0
    for f in sorted(saved.glob(f'extra-{tag}-*/runs/extra-{tag}-*/learnE-*/candidates/rE*/calls/*.json')):
        text = json.loads(f.read_text()).get('reply_text') or ''
        replies += 1
        for m in PATTERN.finditer(text):
            matches += 1
            start = max(0, m.start() - 150)
            print(f.parts[-5], f.parts[-3], '|', text[start:m.end() + 100].replace('\n', ' '))
    print('replies', replies, 'matches', matches)


if __name__ == '__main__':
    main(Path(sys.argv[1]), sys.argv[2])
