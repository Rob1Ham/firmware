"""JSON-lines adapter for pinned BenWestgate/python-codex32 0.6.2.

Run this with its own virtual environment. Never add the firmware testing/
directory to this process's import path: both environments have a bip32 module.
"""

import json
import sys
from importlib.metadata import version
from codex32.bip93 import decode
import codex32

SOURCE_COMMIT = '8ab3bae9e5e0877b74cbaca52b2f05229e172f3e'


def handle(request):
    response = {'implementation': 'BenWestgate/python-codex32',
                'commit': SOURCE_COMMIT, 'package_version': version('codex32'),
                'module_file': codex32.__file__, 'case_id': request['case_id'],
                'operation': request['operation']}
    try:
        if request['operation'] != 'decode_ms':
            raise ValueError('unsupported operation')
        header, seed, pad = decode('ms', request['encoded'])
        response.update(ok=True, header=header, seed_hex=seed.hex(), padding=pad)
    except Exception as exc:
        response.update(ok=False, error_type=type(exc).__name__, error=str(exc))
    return response


for line in sys.stdin:
    request = json.loads(line)
    print(json.dumps(handle(request), sort_keys=True), flush=True)
