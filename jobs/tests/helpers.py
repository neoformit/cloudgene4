"""Test helpers: fixture apps, a fake `nextflow` executable, users."""
import os
import stat
import sys
import textwrap
from pathlib import Path

import shutil
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test.utils import override_settings
from django.contrib.auth.models import Group

from core import config as cloudgene_config
from jobs.management.commands.install_workflow import install_workflow

User = get_user_model()

FAKE_NEXTFLOW = r'''#!{python}
"""Fake nextflow for tests. Behaviour from params.json: fake_mode = success|fail|sleep,
fake_tasks = number of tasks of process SAY."""
import json, os, signal, subprocess, sys, time
args = sys.argv[1:]
def opt(name):
    return args[args.index(name) + 1] if name in args else None
params = json.load(open(opt('-params-file')))
trace, log, work = opt('-with-trace'), opt('-log'), opt('-w')
os.makedirs(work, exist_ok=True)
with open(log, 'w') as fh:
    fh.write('fake nextflow log\n')
env = {{k: v for k, v in os.environ.items() if k.startswith(('CLOUDGENE_', 'FAKE_', 'NXF_'))}}
with open(os.path.join(work, 'invocation.json'), 'w') as fh:
    json.dump({{'argv': args, 'env': env, 'params': params, 'cwd': os.getcwd()}}, fh)
mode = params.get('fake_mode', 'success')
print('[PIPELINE] main.nf | profile=standard', flush=True)
tf = open(trace, 'w')
tf.write('task_id\thash\tnative_id\tprocess\ttag\tname\tstatus\texit\tworkdir\n'); tf.flush()
for i in range(1, int(params.get('fake_tasks', 2)) + 1):
    h = 'ab/%06x' % i
    print('[PROCESS %s] SAY (%d)' % (h, i), flush=True)
    tdir = os.path.join(work, 'ab', '%06x0000' % i)
    os.makedirs(tdir, exist_ok=True)
    with open(os.path.join(tdir, '.command.out'), 'w') as fh:
        fh.write('::message::task %d says hi\n' % i)
    tf.write('%d\t%s\t1\tSAY\t-\tSAY (%d)\tCOMPLETED\t0\t%s\n' % (i, h, i, tdir)); tf.flush()
print('plain output line')
print('::message::hello from stdout')
print('::warning::careful now')
print('::group type=error::')
print('grouped line 1')
print('grouped line 2')
print('::endgroup::', flush=True)
outdir = params.get('outdir')
if outdir:
    os.makedirs(os.path.join(outdir, 'sub dir'), exist_ok=True)
    with open(os.path.join(outdir, 'result.txt'), 'w') as fh:
        fh.write('name=%s\n' % params.get('title', ''))
    with open(os.path.join(outdir, 'sub dir', 'nested ü.txt'), 'w') as fh:
        fh.write('nested\n')
if mode == 'sleep':
    child = subprocess.Popen(['sleep', '300'])
    with open(os.path.join(work, 'child.pid'), 'w') as fh:
        fh.write(str(child.pid))
    print('[PROCESS cd/000001] SLOW (1)', flush=True)
    time.sleep(300)
if mode == 'fail':
    print('ERROR ~ Error executing process > SAY (1)')
    print('')
    print('Caused by: boom')
    print('::error::it failed badly', flush=True)
    sys.exit(1)
sys.exit(0)
'''

BASIC_YAML = """
id: {id}
name: {name}
version: 1.0.0
workflow:
  steps:
    - name: Run it
      script: main.nf
      params:
        fake_mode: {mode}
        fake_tasks: 2
      processes:
        - process: SAY
          label: Saying hello
  inputs:
    - id: title
      description: Title
      type: text
      required: false
  outputs:
    - id: outdir
      description: Results
      type: folder
      download: true
"""


def install_fake_nextflow(tmpdir) -> Path:
    path = Path(tmpdir) / 'nextflow'
    path.write_text(FAKE_NEXTFLOW.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    cloudgene_config.set_value('nextflow.binary', str(path))
    return path


def make_app(app_id, yaml_text=None, *, mode='success', name=None, public=True, groups=(),
             enabled=True, files=None):
    app = cloudgene_config.apps_dir() / app_id
    app.mkdir(parents=True, exist_ok=True)
    text = yaml_text if yaml_text is not None else BASIC_YAML.format(
        id=app_id, name=name or f'App {app_id}', mode=mode)
    (app / 'cloudgene.yaml').write_text(textwrap.dedent(text))
    (app / 'main.nf').write_text('// fake\n')
    for rel, content in (files or {}).items():
        (app / rel).write_text(content)
    return install_workflow(app, public=public, groups=groups, enabled=enabled)


def make_user(username, admin=False, groups=(), password='Passw0rd1'):
    user = User.objects.create_user(username=username, email=f'{username}@example.com',
                                    password=password, full_name=f'{username.title()} Tester')
    if admin:
        user.make_admin()
    for g in groups:
        user.groups.add(Group.objects.get_or_create(name=g)[0])
    return user


def pid_alive(pid) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # zombie?
    try:
        with open(f'/proc/{pid}/stat') as fh:
            return fh.read().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False


class TempHomeMixin:
    """Gives every test its own copy of CLOUDGENE_HOME (settings.yaml, apps/, jobs/)."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.mkdtemp(prefix='cg-test-')
        self.addCleanup(shutil.rmtree, tmp, True)
        home = Path(tmp) / 'home'
        shutil.copytree(settings.CLOUDGENE_HOME, home, ignore=shutil.ignore_patterns('jobs', 'mail'))
        override = override_settings(CLOUDGENE_HOME=home)
        override.enable()
        self.addCleanup(cloudgene_config.clear_cache)
        self.addCleanup(override.disable)
        cloudgene_config.clear_cache()
        self.home = home
