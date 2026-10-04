"""Three separate pytest invocations against one isolated simulator storage.

Run prepare, verify_and_discard, verify_discard in that order, each with a new
simulator process and the same CKCC_SIM_WORKDIR. The harness reports each leg.
"""

import json
import os
from pathlib import Path

from ckcc.protocol import CCProtocolPacker
from codex32 import Share
from constants import simulator_fixed_words


SHARE = Share.from_seed(bytes(range(16)), 'ms', 'rstr', 'a', 2, 0).to_string()


def evidence_path():
    return Path(os.environ['C32_RESTART_EVIDENCE'])


def xpub(dev):
    value = dev.send_recv(CCProtocolPacker.get_xpub(), timeout=5000)
    return value.decode() if isinstance(value, bytes) else value


def test_restart_prepare(change_seed_words, sim_exec, dev):
    change_seed_words(simulator_fixed_words)
    before = xpub(dev)
    assert before.startswith('tpub')
    assert sim_exec('settings.master_set("c32_shares", [%r])' % SHARE) == ''
    assert sim_exec('RV.write(repr(settings.master_get("c32_shares")))') == repr([SHARE])
    persisted = sim_exec('from nvstore import SettingsObject; '
                         'saved = SettingsObject(settings.nvram_key); saved.load(); '
                         'RV.write(repr(saved.get("c32_shares")))')
    assert persisted == repr([SHARE])
    evidence_path().write_text(json.dumps({'xpub': before, 'share': SHARE}) + '\n')


def test_restart_verify_and_discard(sim_exec, dev):
    expected = json.loads(evidence_path().read_text())
    assert xpub(dev) == expected['xpub']
    assert sim_exec('RV.write(repr(settings.master_get("c32_shares")))') == \
        repr([expected['share']])
    assert sim_exec('settings.master_set("c32_shares", [])') == ''
    persisted = sim_exec('from nvstore import SettingsObject; '
                         'saved = SettingsObject(settings.nvram_key); saved.load(); '
                         'RV.write(repr(saved.get("c32_shares")))')
    assert persisted == '[]'


def test_restart_verify_discard(sim_exec, dev):
    expected = json.loads(evidence_path().read_text())
    assert xpub(dev) == expected['xpub']
    assert sim_exec('RV.write(repr(settings.master_get("c32_shares")))') == '[]'
