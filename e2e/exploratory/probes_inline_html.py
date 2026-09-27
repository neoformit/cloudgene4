"""T07b: a job output whose name ends in .html is served as text/html on the app origin
when ``?inline=1`` is used — user-controlled content executing in the viewer's session.

Installs a throw-away app that publishes ``report.html`` containing the user's text input,
runs it as alice, then downloads it inline as alice and as admin.

    BASE=... venv/bin/python -m e2e.exploratory.probes_inline_html <CLOUDGENE_HOME>
"""
import sys
import time
from pathlib import Path

from e2e.exploratory.probe import Client

APP_ID = 't07bhtml'

YAML = """id: %s
name: HTML report fixture
version: 1.0.0
description: T07b probe. Publishes an HTML report built from the user's input.
category: e2e
workflow:
  steps:
    - name: Report
      type: nextflow
      script: main.nf
  inputs:
    - id: message
      description: Message
      type: text
      value: hi
      required: true
  outputs:
    - id: outdir
      description: Report
      type: folder
      download: true
""" % APP_ID

NF = """params.message = 'hi'
params.outdir = 'results'

process REPORT {
    publishDir params.outdir, mode: 'copy'
    input:
    val msg
    output:
    path 'report.html'
    exec:
    task.workDir.resolve('report.html').text = "<html><body><h1>Report</h1>" + msg + "</body></html>"
}

workflow { REPORT(channel.of(params.message)) }
"""


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
    app = home / 'apps' / APP_ID
    app.mkdir(parents=True, exist_ok=True)
    (app / 'cloudgene.yaml').write_text(YAML)
    (app / 'main.nf').write_text(NF)

    admin = Client(user='admin')
    r = admin.post('/api/admin/workflows/install/', json={'path': str(app), 'enabled': True,
                                                          'public': True})
    print('install:', r.status_code, r.text[:160])

    alice = Client(user='alice')
    payload = '<script>document.title="XSS-T07B";fetch("/api/me/")</script>'
    r = alice.post('/api/jobs/', data={'workflow': APP_ID, 'job_name': 'html report',
                                       'message': payload})
    print('submit:', r.status_code, r.text[:120])
    job = r.json()
    print('state:', wait(alice, job['id'])['state'])
    det = alice.get('/api/jobs/%s/' % job['id']).json()
    print('outputs:', [(o['name'], o['path']) for o in det['outputs']])
    oid = det['outputs'][0]['id']
    for who, c in (('alice', alice), ('admin', admin)):
        rr = c.get('/api/jobs/%s/outputs/%s/?inline=1' % (job['id'], oid))
        print('%-6s inline -> %s | %s | %s | payload present: %s'
              % (who, rr.status_code, rr.headers.get('Content-Type'),
                 rr.headers.get('Content-Disposition'), payload in rr.text))
    rr = alice.get('/api/jobs/%s/outputs/%s/' % (job['id'], oid))
    print('alice  attachment -> %s | %s' % (rr.headers.get('Content-Type'),
                                            rr.headers.get('Content-Disposition')))
    alice.delete('/api/jobs/%s/' % job['id'])
    admin.delete('/api/admin/workflows/%s/' % APP_ID)


if __name__ == '__main__':
    main()
