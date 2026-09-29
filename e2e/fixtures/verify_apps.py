#!/usr/bin/env python3
"""Run every fixture app with plain `nextflow run` (no Django) and check its outputs.

Usage:  python e2e/fixtures/verify_apps.py [app ...] [--nextflow /usr/local/bin/nextflow]

Each app is run the way the worker is specified to run it (SPEC §3.3):
`nextflow run main.nf -params-file params.json -w work -with-trace trace.txt -log nextflow.log`.
Prints one line per app with wall-clock time; exits non-zero if any check fails.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APPS = Path(__file__).resolve().parent / 'apps'
FILES = Path(__file__).resolve().parent / 'files'
UNICODE_MESSAGE = 'Grüße "quoted" it\'s $HOME `x` 🚀'


def _trace_rows(trace):
    lines = trace.read_text().splitlines()
    header = lines[0].split('\t')
    return [dict(zip(header, line.split('\t'))) for line in lines[1:]]


def check_hello(ws, params, proc, rows):
    assert proc.returncode == 0, proc.returncode
    assert (Path(params['outdir']) / 'hello.txt').read_text() == UNICODE_MESSAGE + '\n'
    assert '::message::' in proc.stdout
    assert [r['status'] for r in rows] == ['COMPLETED']


def check_all_inputs(ws, params, proc, rows):
    assert proc.returncode == 0, proc.returncode
    out = Path(params['outdir'])
    received = json.loads((out / 'params-received.json').read_text())
    for key, value in params.items():
        assert received[key] == value, (key, received.get(key), value)
    files = json.loads((out / 'files-received.json').read_text())
    assert files['data_file']['name'] == 'my data ü.csv'
    assert files['data_folder']['files'] == ['a.txt', 'b.txt']
    assert files['notes']['content'] == 'line one\nline two\n'


def check_fail(ws, params, proc, rows):
    assert proc.returncode != 0
    assert '::error::Intentional failure' in proc.stdout
    assert [r['status'] for r in rows] == ['FAILED']


def check_slow(ws, params, proc, rows):
    assert proc.returncode == 0
    assert (Path(params['outdir']) / 'slept.txt').read_text().strip() == 'slept %d' % params['seconds']


def check_multi(ws, params, proc, rows):
    assert proc.returncode == 0
    names = sorted({r['name'].split(' ')[0] for r in rows})
    assert names == ['ALIGN', 'CALL', 'REPORT'], names
    assert len(rows) == 15 and all(r['status'] == 'COMPLETED' for r in rows)
    assert len(list(Path(params['outdir']).glob('report_*.txt'))) == 5


def check_command_steps(ws, params, proc, rows):
    # Only the Nextflow step is run here; the command steps are exercised by the E2E tests.
    assert proc.returncode == 0, proc.returncode
    out = Path(params['outdir'])
    assert 'Vault: key-a' in (out / 'run.log').read_text()
    assert (out / 'result.txt').read_text() == 'analyst=%s\n' % params['who']
    assert [r['status'] for r in rows] == ['COMPLETED']


def params_for(app, ws):
    outdir = str(ws / 'output' / 'outdir')
    if app == 'hello':
        return {'message': UNICODE_MESSAGE, 'outdir': outdir}
    if app == 'all-inputs':
        inp = ws / 'input'
        (inp / 'data_file').mkdir(parents=True)
        shutil.copy(FILES / 'my data ü.csv', inp / 'data_file')
        shutil.copytree(FILES / 'folder', inp / 'data_folder')
        (inp / 'notes').mkdir()
        (inp / 'notes' / 'notes.txt').write_text('line one\nline two\n')
        return {
            'text_in': 'hello world ü', 'string_in': 's', 'number_in': 7,
            'notes': str(inp / 'notes' / 'notes.txt'), 'choice': 'c', 'mode': 'accurate',
            'flag': False, 'data_file': str(inp / 'data_file' / 'my data ü.csv'),
            'data_folder': str(inp / 'data_folder'), 'hidden_param': 'hidden-default',
            'agb': True, 'terms': True, 'step_param': 'from-step', 'outdir': outdir,
        }
    if app == 'command-steps':
        return {'who': 'alice@e2e.test', 'label': 'x', 'mode': 'ok', 'outdir': outdir}
    if app == 'slow':
        return {'seconds': int(os.environ.get('SLOW_SECONDS', '60')), 'outdir': outdir}
    if app == 'multi-process':
        return {'tasks': 5, 'outdir': outdir}
    return {'outdir': outdir}


CHECKS = {'hello': check_hello, 'all-inputs': check_all_inputs, 'fail': check_fail,
          'slow': check_slow, 'multi-process': check_multi,
          'command-steps': check_command_steps}


def run_app(app, nextflow, keep):
    ws = Path(tempfile.mkdtemp(prefix='cg-verify-%s-' % app))
    (ws / 'logs').mkdir()
    params = params_for(app, ws)
    (ws / 'params.json').write_text(json.dumps(params, ensure_ascii=False))
    cmd = [nextflow, '-log', str(ws / 'logs' / 'nextflow.log'), 'run', str(APPS / app / 'main.nf'),
           '-params-file', str(ws / 'params.json'), '-w', str(ws / 'work'),
           '-with-trace', str(ws / 'logs' / 'trace.txt'), '-ansi-log', 'false']
    start = time.monotonic()
    proc = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, timeout=600)
    elapsed = time.monotonic() - start
    try:
        CHECKS[app](ws, params, proc, _trace_rows(ws / 'logs' / 'trace.txt'))
        ok, err = True, ''
    except Exception as exc:  # noqa: BLE001 - report any failed check
        ok, err = False, '%s: %s\n--- stdout ---\n%s\n--- stderr ---\n%s' % (
            type(exc).__name__, exc, proc.stdout[-3000:], proc.stderr[-3000:])
    if not keep and ok:
        shutil.rmtree(ws, ignore_errors=True)
    return ok, elapsed, ws, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('apps', nargs='*', default=list(CHECKS))
    ap.add_argument('--nextflow', default=shutil.which('nextflow') or '/usr/local/bin/nextflow')
    ap.add_argument('--keep', action='store_true', help='keep workspaces')
    args = ap.parse_args()
    failed = 0
    for app in args.apps:
        ok, elapsed, ws, err = run_app(app, args.nextflow, args.keep)
        print('%-14s %-4s %6.1fs  %s' % (app, 'OK' if ok else 'FAIL', elapsed, ws if (args.keep or not ok) else ''))
        if not ok:
            failed += 1
            print(err)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
