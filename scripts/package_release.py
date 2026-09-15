"""Package committed application files and verified H5 only, never private working-tree files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise RuntimeError('Commit and review the release before packaging; working tree is not clean')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    subprocess.run(['node', 'frontend/scripts/check-build.mjs', '--both'], cwd=ROOT, check=True)
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    names = [name for name in tracked if name.startswith(('backend/app/', 'deploy/')) or name in
             ('backend/requirements.txt', '.dockerignore')]
    built = sorted((ROOT / 'frontend/dist/h5').rglob('*'))
    config = dotenv_values(ROOT / 'backend/.env')
    secrets = [value.encode() for key, value in config.items() if value and len(value) >= 8 and
               any(word in key for word in ('KEY', 'SECRET', 'PASSWORD'))]
    folder = ROOT / '.local/releases'
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (revision + '.tar.gz')
    manifest = []
    with tarfile.open(destination, 'w:gz') as archive:
        for name in names + [path.relative_to(ROOT).as_posix() for path in built if path.is_file()]:
            path = ROOT / name
            if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
                raise RuntimeError('Release contains a symlink or escaped path')
            data = path.read_bytes()
            if any(secret in data for secret in secrets) or (b'-----BEGIN ' + b'PRIVATE KEY-----') in data:
                raise RuntimeError('Private credential match in release; packaging stopped')
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
            manifest.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    result = {'revision': revision, 'archive_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
              'archive_bytes': destination.stat().st_size, 'files': manifest}
    destination.with_suffix('.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({'revision': revision, 'files': len(manifest), 'bytes': result['archive_bytes'], 'private_matches': 0}))


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error) if isinstance(error, RuntimeError) else 'Release verification command failed') from None
