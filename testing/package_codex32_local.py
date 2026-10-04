"""Package a qualified, locally tagged Codex32 test build without signing.

The report names every build/evidence file and SHA256. This command verifies
them and creates a deterministic archive; it never tags, pushes or flashes.
"""

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def add_file(archive, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ''
    info.mode = 0o644
    archive.addfile(info, __import__('io').BytesIO(data))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    commit = git('rev-parse', 'HEAD')
    if not report.get('qualified') or report.get('source_commit') != commit:
        parser.error('qualification report is incomplete or names another commit')
    if git('status', '--porcelain', '--ignore-submodules=dirty'):
        parser.error('source tree has uncommitted changes')
    if git('cat-file', '-t', 'refs/tags/' + args.tag) != 'tag':
        parser.error('release tag must be annotated')
    if git('rev-list', '-n', '1', args.tag) != commit:
        parser.error('release tag does not identify tested source commit')
    files = {}
    for item in report['package_files']:
        source = Path(item['path']).resolve()
        if not source.is_file() or sha256(source) != item['sha256']:
            parser.error(f'missing or changed package input: {source}')
        name = item['name']
        if name in files or name.startswith('/') or '..' in Path(name).parts:
            parser.error(f'duplicate or unsafe archive name: {name}')
        files[name] = source.read_bytes()
    files['source-commit.txt'] = (commit + '\n').encode()
    files['tag.txt'] = (args.tag + '\n').encode()
    files['qualification-report.json'] = args.report.read_bytes()
    checksum_lines = [f'{hashlib.sha256(files[name]).hexdigest()}  {name}'
                      for name in sorted(files)]
    files['SHA256SUMS'] = ('\n'.join(checksum_lines) + '\n').encode()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        parser.error('archive already exists; choose a new local filename')
    with output.open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w') as archive:
                for name in sorted(files):
                    add_file(archive, name, files[name])
    print(json.dumps({'archive': str(output), 'sha256': sha256(output),
                      'source_commit': commit, 'tag': args.tag,
                      'files': len(files)}, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
