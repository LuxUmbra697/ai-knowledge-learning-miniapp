"""Generate universal hash locks, constrained to this verified environment's installed versions."""
import argparse
from importlib.metadata import distributions
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main(uv):
    if sys.version_info[:2] != (3, 13):
        raise SystemExit('Lock regeneration requires the verified Python 3.13 environment')
    private = ROOT / '.local/locks'
    private.mkdir(parents=True, exist_ok=True)
    constraints = private / 'installed-constraints.txt'
    constraints.write_text('\n'.join(sorted({f'{item.metadata["Name"]}=={item.version}' for item in distributions()})) + '\n', encoding='utf8')
    for name in ('requirements', 'requirements-dev'):
        subprocess.run([uv, 'pip', 'compile', str(ROOT / f'backend/{name}.in'), '--constraint', str(constraints),
                        '--python-version', '3.13', '--universal', '--generate-hashes', '--no-header',
                        '--no-annotate', '--output-file', str(ROOT / f'backend/{name}.txt')], check=True, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--uv', default='uv')
    main(parser.parse_args().uv)
