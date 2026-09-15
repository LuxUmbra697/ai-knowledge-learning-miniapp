"""Use an existing local Git Credential Manager login; never echo or upload credentials."""
import argparse
import json
import os
from pathlib import Path
import subprocess

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPO = 'LuxUmbra697/ai-knowledge-learning-miniapp'
BRANCH = 'codex/learning-studio-upgrade'


def client():
    environment = dict(os.environ, GCM_INTERACTIVE='never', GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, env=environment, cwd=ROOT, timeout=20)
    values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line) if result.returncode == 0 else {}
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    if values.get('password'):
        headers['Authorization'] = 'Bearer ' + values['password']
    return httpx.Client(base_url='https://api.github.com/', headers=headers, timeout=20, trust_env=False), bool(values.get('password'))


def main(mode):
    api, authenticated = client()
    with api:
        if mode == 'inspect':
            response = api.get('repos/' + REPO)
            if response.status_code != 200:
                raise RuntimeError(f'GitHub repository inspection returned HTTP {response.status_code}')
            data = response.json()
            print(json.dumps({'authenticated': authenticated, 'repository': data['full_name'], 'default_branch': data['default_branch'],
                              'can_push': data.get('permissions', {}).get('push'), 'public': not data['private']}))
        elif mode == 'ci':
            response = api.get(f'repos/{REPO}/actions/runs', params={'branch': BRANCH, 'per_page': 5})
            if response.status_code != 200:
                raise RuntimeError(f'GitHub Actions inspection returned HTTP {response.status_code}')
            print(json.dumps([{'id': row['id'], 'sha': row['head_sha'], 'status': row['status'], 'conclusion': row['conclusion'], 'url': row['html_url']}
                              for row in response.json()['workflow_runs']]))
        elif mode == 'pr':
            if not authenticated:
                raise RuntimeError('No existing GitHub HTTPS credential; SSH push may still work')
            response = api.get(f'repos/{REPO}/pulls', params={'state': 'open', 'head': 'LuxUmbra697:' + BRANCH})
            if response.status_code != 200:
                raise RuntimeError(f'GitHub PR lookup returned HTTP {response.status_code}')
            rows = response.json()
            if rows:
                result = rows[0]
            else:
                response = api.post(f'repos/{REPO}/pulls', json={'title': 'Upgrade the evidence-based learning loop and companion experience',
                    'head': BRANCH, 'base': 'main', 'draft': True,
                    'body': '## Scope\nOwned hybrid RAG, durable bounded learning tasks, five configurable question types, authoritative assessment, FSRS/BKT reviews, confirmed plans, Mermaid review maps, named notebooks, and isolated character memories.\n\n## Verification\nDeterministic backend/MySQL/frontend regression and actual H5 flows are included. Provider tests are explicit and budgeted; no provider or deployment credentials are uploaded. Native-device and production status must be checked against the current README before release.\n\n## Review boundaries\nExisting repository history and third-party attribution are retained. Production deployment is separate from CI and must preserve all existing gateway routes and data.'})
                if response.status_code != 201:
                    raise RuntimeError(f'GitHub PR creation returned HTTP {response.status_code}')
                result = response.json()
            print(json.dumps({'number': result['number'], 'url': result['html_url'], 'draft': result['draft']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['inspect', 'ci', 'pr'])
    try:
        main(parser.parse_args().mode)
    except (RuntimeError, httpx.HTTPError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error) if isinstance(error, RuntimeError) else f'GitHub operation failed: {type(error).__name__}') from None
