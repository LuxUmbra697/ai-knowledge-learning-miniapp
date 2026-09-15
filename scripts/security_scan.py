"""Scan the actual Git index against configured secrets without printing values."""
from pathlib import Path
import re
import subprocess
import sys

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = dotenv_values(ROOT / 'backend/.env')
    secrets = [value.encode() for key, value in config.items() if value and len(value) >= 8 and re.search(r'KEY|SECRET|PASSWORD', key)]
    files = subprocess.check_output(['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'], cwd=ROOT).split(b'\0')
    findings = []
    count = 0
    for raw in files:
        if not raw:
            continue
        name = raw.decode('utf-8')
        data = subprocess.check_output(['git', 'show', ':' + name], cwd=ROOT)
        count += 1
        if any(secret in data for secret in secrets) or re.search(rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----', data):
            findings.append(name)
        if re.search(r'(^|/)(\.env|backend\.env|LOCAL_.*|project\.private\.config\.json)$', name):
            findings.append(name)
    print(f'Staged files scanned: {count}; sensitive matches: {len(findings)}')
    for name in findings:
        print('BLOCKED: ' + name)
    return bool(findings)


if __name__ == '__main__':
    sys.exit(main())
