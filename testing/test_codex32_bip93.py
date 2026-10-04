# (c) Copyright 2026 by Coinkite Inc. This file is covered by license found in COPYING-CC.
"""Host-only BIP 93 conformance tests. Run with --noconftest and PYTHONPATH=testing."""

import itertools
import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))
from codex32 import CHARSET, Share, generate_share  # noqa: E402
from bip32 import BIP32Node  # noqa: E402

VECTORS = json.loads((ROOT / 'testing/fixtures/codex32-bip93-vectors.json').read_text())
assert VECTORS['source']['commit'] == '927b6de9915c9262615a6399de51b200f81e5aa4'
assert VECTORS['source']['sha256'] == 'c847c6e513b64ee6ab10975690757d64a875f77c0e75866a86b733f3985784ec'
assert len(VECTORS['valid']) == 34 and len(VECTORS['invalid']) == 55

EXPECTED_SEEDS = {
    'ms10testsxxxxxxxxxxxxxxxxxxxxxxxxxx4nzvca9cmczlw':
        '318c6318c6318c6318c6318c6318c631',
    'MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW':
        'd1808e096b35b209ca12132b264662a5',
    'ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6nln':
        'ffeeddccbbaa99887766554433221100',
    'ms10leetsllhdmn9m42vcsamx24zrxgs3qrl7ahwvhw4fnzrhve25gvezzyqqtum9pgv99ycma':
        'ffeeddccbbaa99887766554433221100ffeeddccbbaa99887766554433221100',
    'MS100C8VSM32ZXFGUHPCHTLUPZRY9X8GF2TVDW0S3JN54KHCE6MUA7LQPZYGSFJD6AN074RXVCEMLH8WU3TK925ACDEFGHJKLMNPQRSTUVWXY06FHPV80UNDVARHRAK':
        'dc5423251cb87175ff8110c8531d0952d8d73e1194e95b5f19d6f9df7c01111104c9baecdfea8cccc677fb9ddc8aec5553b86e528bcadfdcc201c17c638c47e9',
    'ms10seedsqqqsyqcyq5rqwzqfpg9scrgwpugpzysn9vaqzzvs20xnl':
        '000102030405060708090a0b0c0d0e0f10111213',
    'ms10seedsyqsjygeyy5nzw2pf9g4jctfw9ucrzv3nxs6nvdau84gz0632s0xs':
        '202122232425262728292a2b2c2d2e2f3031323334353637',
    'ms10seedsgpq5ys6yg4rywjzfff95cn2wfag9z5jn2324v46ct9d9hrcduqw8c3lccl':
        '404142434445464748494a4b4c4d4e4f505152535455565758595a5b',
}

EXPECTED_ROOTS = {
    16: 'xprv9s21ZrQH143K3taPNekMd9oV5K6szJ8ND7vVh6fxicRUMDcChr3bFFzuxY8qP3xFFBL6DWc2uEYCfBFZ2nFWbAqKPhtCLRjgv78EZJDEfpL',
    17: 'xprv9s21ZrQH143K2NkobdHxXeyFDqE44nJYvzLFtsriatJNWMNKznGoGgW5UMTL4fyWtajnMYb5gEc2CgaKhmsKeskoi9eTimpRv2N11THhPTU',
    18: 'xprv9s21ZrQH143K266qUcrDyYJrSG7KA3A7sE5UHndYRkFzsPQ6xwUhEGK1rNuyyA57Vkc1Ma6a8boVqcKqGNximmAe9L65WsYNcNitKRPnABd',
    19: 'xprv9s21ZrQH143K3s41UCWxXTsU4TRrhkpD1t21QJETan3hjo8DP5LFdFcB5eaFtV8x6Y9aZotQyP8KByUjgLTbXCUjfu2iosTbMv98g8EQoqr',
    20: 'xprv9s21ZrQH143K4UYT4rP3TZVKKbmRVmfRqTx9mG2xCy2JYipZbkLV8rwvBXsUbEv9KQiUD7oED1Wyi9evZzUn2rqK9skRgPkNaAzyw3YrpJN',
}


@pytest.mark.parametrize('vector', VECTORS['valid'], ids=lambda v: v['id'])
def test_all_published_valid_strings(vector):
    text = vector['encoded']
    share = Share.parse(text)
    assert share.to_string().lower() == text.lower()
    assert Share.parse(share.to_string()) == share
    assert len(share) == len(text)


@pytest.mark.parametrize('vector', VECTORS['invalid'], ids=lambda v: v['id'])
def test_all_published_invalid_strings(vector):
    with pytest.raises((AssertionError, ValueError)):
        Share.parse(vector['encoded'])


@pytest.mark.parametrize('text,expected', EXPECTED_SEEDS.items())
def test_published_master_seed_and_padding(text, expected):
    share = Share.parse(text)
    seed, pad = share.to_seed_and_pad()
    assert seed.hex() == expected
    assert Share.from_seed(seed, share.hrp, share.uid, share.index,
                           share.threshold, pad).to_string().lower() == text.lower()


@pytest.mark.parametrize('invalid_pad', [-1, 1])
def test_160_bit_seed_has_no_padding_bits(invalid_pad):
    with pytest.raises(AssertionError, match='invalid padding'):
        Share.from_seed(bytes(range(20)), 'ms', 'test', 's', 0, invalid_pad)


@pytest.mark.parametrize('text,root', zip(list(EXPECTED_SEEDS)[:5], EXPECTED_ROOTS.values()))
def test_published_bip32_root(text, root):
    seed, _ = Share.parse(text).to_seed_and_pad()
    assert BIP32Node.from_master_secret(seed, netcode='BTC').hwif(as_private=True) == root


def test_vector_2_recovery_and_derivation():
    a = Share.parse('MS12NAMEA320ZYXWVUTSRQPNMLKJHGFEDCAXRPP870HKKQRM')
    c = Share.parse('MS12NAMECACDEFGHJKLMNPQRSTUVWXYZ023FTR2GDZMPY6PN')
    expected = 'MS12NAMES6XQGUZTTXKEQNJSJZV4JV3NZ5K3KWGSPHUH6EVW'
    derived = 'MS12NAMEDLL4F8JLH4E5VDVULDLFXU2JHDNLSM97XVENRXEG'
    assert generate_share([a, c], 's').to_string() == expected
    assert generate_share([c, a], 'd').to_string() == derived


def test_vector_3_all_ten_subsets():
    shares = [Share.parse(value) for value in (
        'ms13casha320zyxwvutsrqpnmlkjhgfedca2a8d0zehn8a0t',
        'ms13cashcacdefghjklmnpqrstuvwxyz023949xq35my48dr',
        'ms13cashd0wsedstcdcts64cd7wvy4m90lm28w4ffupqs7rm',
        'ms13casheekgpemxzshcrmqhaydlp6yhms3ws7320xyxsar9',
        'ms13cashf8jh6sdrkpyrsp5ut94pj8ktehhw2hfvyrj48704',
    )]
    expected = 'ms13cashsllhdmn9m42vcsamx24zrxgs3qqjzqud4m0d6nln'
    for subset in itertools.combinations(shares, 3):
        assert generate_share(subset, 's').to_string().lower() == expected


@pytest.mark.parametrize('size', [16, 20, 24, 28, 32, 64])
def test_deterministic_threshold_and_padding_properties(size):
    # 1,000 reproducible cases per BIP 93 size, spanning thresholds 2..9.
    rng = random.Random(930000 + size)
    pad_bits = (-size * 8) % 5
    for case in range(1000):
        threshold = 2 + (case % 8)
        identifier = ''.join(rng.choice(CHARSET) for _ in range(4))
        seed = rng.randbytes(size)
        pad = rng.randrange(1 << pad_bits)
        secret = Share.from_seed(seed, 'ms', identifier, 's', threshold, pad)
        assert Share.parse(secret.to_string()).to_seed_and_pad() == (seed, pad)
        basis = [secret]
        for index in 'acdefghj'[:threshold - 1]:
            basis.append(Share.from_seed(rng.randbytes(size), 'ms', identifier,
                                         index, threshold, rng.randrange(1 << pad_bits)))
        derived = generate_share(basis, 'k')
        recovered = generate_share(basis[1:] + [derived], 's')
        assert recovered == secret, (size, case)
        assert generate_share([derived] + list(reversed(basis[1:])), 's') == secret
        if case < 8:
            with pytest.raises(AssertionError, match='need exactly'):
                generate_share(basis[1:], 's')
            with pytest.raises(AssertionError, match='need exactly'):
                generate_share(basis + [derived], 'z')
