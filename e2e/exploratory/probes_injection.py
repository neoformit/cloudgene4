"""T07b: K3 / command-injection probes — job names and text inputs must never reach a
path or a shell, and must come back intact through the API.

    BASE=... venv/bin/python -m e2e.exploratory.probes_injection <CLOUDGENE_HOME>
"""
import json
import sys
import time
from pathlib import Path

from e2e.exploratory.probe import Client

RESULTS = []
MARKERS = ('/tmp/t07b-pwned-name', '/tmp/t07b-pwned-msg')


def check(name, ok, evidence=''):
    RESULTS.append((name, ok))
    print('%-5s %-58s %s' % ('PASS' if ok else 'FAIL', name, evidence), flush=True)


def wait(c, job_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = c.get('/api/jobs/%s/status/' % job_id).json()
        if s['state'] in ('success', 'failed', 'cancelled'):
            return s
        time.sleep(1)
    raise SystemExit('timeout')


def main():
    home = Path(sys.argv[1])
    for m in MARKERS:
        Path(m).unlink(missing_ok=True)
    alice = Client(user='alice')

    evil_name = '$(touch /tmp/t07b-pwned-name) `id` ; rm -rf / & | ../../etc/passwd %s ${HOME}'
    evil_msg = "'; touch /tmp/t07b-pwned-msg; echo '"
    r = alice.post('/api/jobs/', data={'workflow': 'hello', 'job_name': evil_name,
                                       'message': evil_msg})
    check('injection: job with shell metacharacters accepted', r.status_code == 201, r.text[:150])
    job = r.json()
    check('injection: name stored verbatim', job['name'] == evil_name, repr(job['name']))
    state = wait(alice, job['id'])
    check('injection: job still runs', state['state'] == 'success', state['state'])
    for m in MARKERS:
        check('injection: no shell side effect (%s)' % m, not Path(m).exists())

    ws = home / 'jobs' / job['id']
    check('injection: workspace is keyed by the uuid', ws.is_dir(), str(ws))
    siblings = [p.name for p in (home / 'jobs').iterdir()]
    check('injection: no workspace named after the job name',
          not any('pwned' in s or 'passwd' in s or '$' in s for s in siblings),
          str(siblings[:5]))
    params = json.loads((ws / 'params.json').read_text())
    check('injection: params.json keeps the value verbatim', params.get('message') == evil_msg,
          repr(params.get('message')))
    check('injection: job name is not in params.json',
          'pwned-name' not in json.dumps(params), json.dumps(params)[:120])
    out = alice.get('/api/jobs/%s/' % job['id']).json()['outputs']
    body = alice.get('/api/jobs/%s/outputs/%s/' % (job['id'], out[0]['id'])).text
    check('injection: pipeline wrote the literal text', body.strip() == evil_msg.strip(),
          repr(body[:80]))

    # control characters and newlines in the job name are stripped (K3)
    r = alice.post('/api/jobs/', data={'workflow': 'hello',
                                       'job_name': 'line1\nline2\x00\x07 tail', 'message': 'x'})
    name = r.json()['name']
    check('injection: control characters stripped from the name',
          '\n' not in name and '\x00' not in name, repr(name))
    alice.delete('/api/jobs/%s/' % r.json()['id'])

    # NUL and traversal in a text input
    r = alice.post('/api/jobs/', data={'workflow': 'hello', 'job_name': 'traversal',
                                       'message': '../../../../etc/passwd'})
    check('injection: traversal-looking text input is just text', r.status_code == 201,
          r.text[:100])
    if r.status_code == 201:
        st = wait(alice, r.json()['id'])
        det = alice.get('/api/jobs/%s/' % r.json()['id']).json()
        content = alice.get('/api/jobs/%s/outputs/%s/'
                            % (det['id'], det['outputs'][0]['id'])).text if det['outputs'] else ''
        check('injection: no /etc/passwd content in the output',
              'root:x:' not in content, content[:60])
        alice.delete('/api/jobs/%s/' % det['id'])

    # the download must not be servable as active content
    det = alice.get('/api/jobs/%s/' % job['id']).json()
    r = alice.get('/api/jobs/%s/outputs/%s/?inline=1' % (job['id'], det['outputs'][0]['id']))
    print('INFO  inline download headers: %s | %s'
          % (r.headers.get('Content-Type'), r.headers.get('Content-Disposition')))
    r2 = alice.get('/api/jobs/%s/outputs/%s/' % (job['id'], det['outputs'][0]['id']))
    print('INFO  attachment download headers: %s | %s | nosniff=%s'
          % (r2.headers.get('Content-Type'), r2.headers.get('Content-Disposition'),
             r2.headers.get('X-Content-Type-Options')))
    r3 = alice.get('/api/jobs/%s/log/' % job['id'])
    print('INFO  log headers: %s | nosniff=%s'
          % (r3.headers.get('Content-Type'), r3.headers.get('X-Content-Type-Options')))

    alice.delete('/api/jobs/%s/' % job['id'])
    failed = [n for n, ok in RESULTS if not ok]
    print('\n%d/%d checks passed' % (len(RESULTS) - len(failed), len(RESULTS)))
    for n in failed:
        print('  FAILED:', n)


if __name__ == '__main__':
    main()
