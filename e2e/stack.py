"""Boot and tear down the full Cloudgene stack for E2E tests.

One stack per pytest process (per xdist worker): temp CLOUDGENE_HOME under
`e2e/.artifacts/stack-<worker>/`, `manage.py runserver` serving the production SPA bundle, and
`manage.py run_worker` when that command exists. Nothing here imports Django.

Database: SQLite by default (a file under the stack's root, as before). Set `E2E_DATABASE_URL`
(e.g. `postgres://cloudgene:cloudgene@127.0.0.1:5432/cloudgene`) to run the whole suite against
Postgres instead — each stack (one per xdist worker) gets its own database, named after the
worker (`<database-from-the-url>_e2e_<worker>`), created at start-up and dropped at teardown, so
parallel workers never collide and a run never touches the URL's own database. Requires
`psycopg2` (already in requirements.txt) and a reachable server with CREATEDB privilege for the
given role.
"""
import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
import yaml

from e2e import constants

REPO = Path(__file__).resolve().parent.parent
E2E_DIR = REPO / 'e2e'
ARTIFACTS = Path(os.environ.get('E2E_ARTIFACTS', E2E_DIR / '.artifacts'))
FIXTURE_APPS = E2E_DIR / 'fixtures' / 'apps'
FRONTEND = REPO / 'frontend'
BUNDLE = REPO / 'static' / 'frontend'
PYTHON = os.environ.get('E2E_PYTHON', sys.executable)
OUTBOX_DIRNAME = 'mail'  # file-backend outbox = $CLOUDGENE_HOME/mail (settings.yaml + Django default)
NEXTFLOW = os.environ.get('E2E_NEXTFLOW') or shutil.which('nextflow') or '/usr/local/bin/nextflow'
E2E_DATABASE_URL = os.environ.get('E2E_DATABASE_URL')


# ------------------------------------------------------------------------------------------------
# Postgres: one database per stack (xdist worker), created at start-up, dropped at teardown.
# ------------------------------------------------------------------------------------------------

def _pg_admin_connect(base_url):
    """Connect to the server named by `base_url` (any of its databases will do for admin
    statements like CREATE/DROP DATABASE), autocommit (required for those statements)."""
    import psycopg2
    parts = urlsplit(base_url)
    conn = psycopg2.connect(
        host=parts.hostname or '127.0.0.1', port=parts.port or 5432,
        user=parts.username, password=parts.password,
        dbname=(parts.path or '/postgres').lstrip('/') or 'postgres',
    )
    conn.autocommit = True
    return conn


def _pg_db_name(base_url, worker):
    base_name = (urlsplit(base_url).path or '/cloudgene').lstrip('/') or 'cloudgene'
    return '%s_e2e_%s' % (base_name, worker)


def _pg_url_for(base_url, db_name):
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, '/' + db_name, '', ''))


def pg_create_database(base_url, db_name):
    """Drop (if left over from a killed run) and (re)create `db_name` on the server in
    `base_url`. Terminates any lingering backends first so a stale connection never blocks it."""
    conn = _pg_admin_connect(base_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (db_name,))
            cur.execute('DROP DATABASE IF EXISTS "%s"' % db_name)
            cur.execute('CREATE DATABASE "%s"' % db_name)
    finally:
        conn.close()


def pg_drop_database(base_url, db_name):
    conn = _pg_admin_connect(base_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (db_name,))
            cur.execute('DROP DATABASE IF EXISTS "%s"' % db_name)
    finally:
        conn.close()


class StackError(RuntimeError):
    pass


def _tail(path, lines=60):
    try:
        return '\n'.join(Path(path).read_text(errors='replace').splitlines()[-lines:])
    except OSError:
        return '<no log>'


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------------------------------------
# Frontend bundle
# ------------------------------------------------------------------------------------------------

def _newest_source_mtime():
    paths = [FRONTEND / 'index.html', FRONTEND / 'vite.config.js', FRONTEND / 'package.json']
    paths += [p for p in (FRONTEND / 'src').rglob('*') if p.is_file()]
    paths += [p for p in (FRONTEND / 'public').rglob('*') if p.is_file()] if (FRONTEND / 'public').exists() else []
    return max(p.stat().st_mtime for p in paths if p.exists())


def ensure_frontend_built(log_dir):
    """Build the SPA once if sources are newer than the bundle (file-locked across xdist workers)."""
    if os.environ.get('E2E_SKIP_BUILD') == '1':
        return
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACTS / '.build.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        index = BUNDLE / 'index.html'
        fresh = index.exists() and index.stat().st_mtime >= _newest_source_mtime()
        if fresh:
            return
        if not (FRONTEND / 'node_modules').exists():
            raise StackError('frontend/node_modules missing: run `npm install` in frontend/ '
                             '(or set E2E_SKIP_BUILD=1 to use an existing static/frontend bundle)')
        cmd = ['npm', 'run', 'build']
        log = Path(log_dir) / 'frontend-build.log'
        with open(log, 'w') as fh:
            proc = subprocess.run(cmd, cwd=FRONTEND, stdout=fh, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            raise StackError('Frontend build failed (%s). Log: %s\n%s' % (' '.join(cmd), log, _tail(log, 40)))


# ------------------------------------------------------------------------------------------------
# CLOUDGENE_HOME
# ------------------------------------------------------------------------------------------------

def settings_yaml(base_url):
    """settings.yaml (schema: core/config.py, SPEC §3.2) with small limits for fast queue tests."""
    return {
        'server': {
            'name': constants.SERVER_NAME,
            'url': base_url,
            'max_running_jobs': constants.MAX_RUNNING_JOBS,
            'max_queue_size': constants.MAX_QUEUE_SIZE,
            'maintenance': False,
            'maintenance_message': 'E2E maintenance',
            'job_retention_days': 7,
            'max_upload_mb': 50,
        },
        'queue': {'paused': False},
        'security': {'max_login_attempts': 5, 'lockout_duration': 60, 'require_activation': True},
        'mail': {
            'backend': 'file',
            'file_path': OUTBOX_DIRNAME,  # relative to CLOUDGENE_HOME
            'from_email': 'noreply@e2e.test',
        },
        'nextflow': {'binary': NEXTFLOW},
        'navbar': constants.NAVBAR,
        'apps': [
            {'path': app_id, 'enabled': True, 'public': rules['public'], 'groups': rules['groups']}
            for app_id, rules in constants.APPS.items()
        ],
    }


PAGES = {
    'home.html': '<div class="container"><h1>%s</h1><p>%s</p></div>' % (constants.SERVER_NAME,
                                                                       constants.PAGE_MARKERS['home']),
    'footer.html': '<span>%s</span> &middot; <a href="/pages/about">About</a>' % constants.PAGE_MARKERS['footer'],
    'about.html': '<h2>About</h2><p>%s</p>' % constants.PAGE_MARKERS['about'],
}


def build_home(home, base_url):
    for sub in ('config', 'pages', 'apps', 'jobs'):
        (home / sub).mkdir(parents=True, exist_ok=True)
    (home / 'config' / 'settings.yaml').write_text(
        yaml.safe_dump(settings_yaml(base_url), sort_keys=False, allow_unicode=True))
    (home / 'config' / 'nextflow.config').write_text('// global Nextflow config (E2E)\n')
    (home / 'config' / 'nextflow.env').write_text('')
    for name, html in PAGES.items():
        (home / 'pages' / name).write_text(html + '\n')
    for app_id in constants.APPS:
        shutil.copytree(FIXTURE_APPS / app_id, home / 'apps' / app_id)


# ------------------------------------------------------------------------------------------------
# Stack
# ------------------------------------------------------------------------------------------------

@dataclass
class Stack:
    name: str
    root: Path
    base_url: str
    env: dict
    home: Path
    outbox_dir: Path
    db_path: Path | None
    log_dir: Path
    worker_available: bool = False
    worker_skip_reason: str = ''
    health_endpoint: bool = False
    procs: dict = field(default_factory=dict)
    pg_admin_url: str | None = None  # set when running on Postgres (E2E_DATABASE_URL)
    pg_db_name: str | None = None

    # -- process helpers -------------------------------------------------------------------------
    def manage(self, *args, check=True, timeout=300, log_name=None):
        """Run `manage.py <args>` with the stack env; returns CompletedProcess (text)."""
        proc = subprocess.run([PYTHON, 'manage.py', *args], cwd=REPO, env=self.env,
                              capture_output=True, text=True, timeout=timeout)
        if log_name:
            (self.log_dir / log_name).write_text(proc.stdout + proc.stderr)
        if check and proc.returncode != 0:
            raise StackError('manage.py %s failed (%s):\n%s\n%s' % (
                ' '.join(args), proc.returncode, proc.stdout[-3000:], proc.stderr[-3000:]))
        return proc

    def django_shell(self, code, check=True):
        """Run Python code inside Django (`manage.py shell -c`) and return its stdout."""
        return self.manage('shell', '-c', code, check=check).stdout

    def run_seed(self, *steps):
        proc = subprocess.run([PYTHON, '-m', 'e2e.seed', *steps], cwd=REPO, env=self.env,
                              capture_output=True, text=True, timeout=300)
        with open(self.log_dir / 'seed.log', 'a') as fh:
            fh.write(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            raise StackError('seed %s failed:\n%s\n%s' % (steps, proc.stdout[-3000:], proc.stderr[-3000:]))
        return proc.stdout

    def _spawn(self, key, args):
        log = open(self.log_dir / ('%s.log' % key), 'ab')
        proc = subprocess.Popen([PYTHON, 'manage.py', *args], cwd=REPO, env=self.env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        self.procs[key] = proc
        return proc

    def _alive(self, key):
        proc = self.procs.get(key)
        return proc is not None and proc.poll() is None

    # -- config ------------------------------------------------------------------------------------
    @property
    def settings_path(self):
        return self.home / 'config' / 'settings.yaml'

    def read_settings(self):
        return yaml.safe_load(self.settings_path.read_text())

    def write_settings(self, data):
        tmp = self.settings_path.with_suffix('.tmp')
        tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        os.replace(tmp, self.settings_path)

    # -- health ------------------------------------------------------------------------------------
    def health(self):
        """Return (status_code, json_or_None) of /api/health."""
        r = requests.get(self.base_url + '/api/health', timeout=5)
        try:
            payload = r.json()
        except ValueError:
            payload = None
        return r.status_code, payload

    def wait_ready(self, timeout=90):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            if not self._alive('server'):
                raise StackError('runserver exited during start-up:\n' + _tail(self.log_dir / 'server.log'))
            try:
                code, payload = self.health()
                if code == 200:
                    self.health_endpoint = True
                    return payload
                if code == 404 or (code >= 300 and payload is None):
                    # No health endpoint yet (pre-T01): fall back to the SPA root.
                    r = requests.get(self.base_url + '/', timeout=5)
                    if r.status_code == 200:
                        return None
                last = 'health %s %s' % (code, payload)
            except requests.RequestException as exc:
                last = repr(exc)
            time.sleep(0.25)
        raise StackError('stack not ready after %ss (%s)\n%s' % (timeout, last, _tail(self.log_dir / 'server.log')))

    def wait_worker_heartbeat(self, timeout=30):
        """If /api/health reports on the worker, wait until it says the worker is alive."""
        if not self.health_endpoint:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._alive('worker'):
                raise StackError('run_worker exited during start-up:\n' + _tail(self.log_dir / 'worker.log'))
            _, payload = self.health()
            if worker_ok(payload) is not False:
                return
            time.sleep(0.5)
        raise StackError('worker heartbeat not reported by /api/health within %ss: %s' % (timeout, payload))

    def require_worker(self):
        """Skip the calling test when no worker process runs (e.g. before T03 lands)."""
        import pytest
        if not self.worker_available:
            pytest.skip(self.worker_skip_reason)
        if not self._alive('worker'):
            pytest.fail('worker process died; see %s' % (self.log_dir / 'worker.log'))

    def stop(self):
        for key, proc in list(self.procs.items()):
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=15)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
        self.procs.clear()
        if self.pg_admin_url and self.pg_db_name:
            # Web/worker processes above are dead, so their connections are already gone; drop
            # the per-stack database so a run never leaves databases behind.
            pg_drop_database(self.pg_admin_url, self.pg_db_name)


def worker_ok(payload):
    """Interpret the worker part of a /api/health payload: True/False, or None if not reported."""
    if not isinstance(payload, dict) or 'worker' not in payload:
        return None
    w = payload['worker']
    if isinstance(w, bool):
        return w
    if isinstance(w, str):
        return w.lower() in ('ok', 'up', 'alive', 'running')
    if isinstance(w, dict):
        if 'ok' in w:
            return bool(w['ok'])
        if 'alive' in w:
            return bool(w['alive'])
        if 'status' in w:
            return str(w['status']).lower() in ('ok', 'up', 'alive', 'running')
    return None


def start_stack(name='main'):
    root = ARTIFACTS / ('stack-%s' % name)
    if root.exists():
        shutil.rmtree(root)
    log_dir = root / 'logs'
    log_dir.mkdir(parents=True)
    home = root / 'home'
    outbox = home / OUTBOX_DIRNAME
    port = free_port()
    base_url = 'http://127.0.0.1:%d' % port

    ensure_frontend_built(log_dir)
    build_home(home, base_url)
    outbox.mkdir()

    db_path = None
    pg_db_name = None
    if E2E_DATABASE_URL:
        pg_db_name = _pg_db_name(E2E_DATABASE_URL, name)
        pg_create_database(E2E_DATABASE_URL, pg_db_name)
        database_url = _pg_url_for(E2E_DATABASE_URL, pg_db_name)
    else:
        db_path = root / 'db.sqlite3'
        database_url = 'sqlite:///' + str(db_path)  # absolute path -> sqlite:////...

    env = dict(os.environ)
    env.update({
        'DJANGO_SETTINGS_MODULE': 'cloudgene_django.settings',
        'CLOUDGENE_HOME': str(home),
        'DATABASE_URL': database_url,
        'LOG_LEVEL': os.environ.get('E2E_LOG_LEVEL', 'INFO'),
        'DJANGO_SECRET_KEY': 'e2e-not-secret-' + name,
        'DEBUG': os.environ.get('E2E_DEBUG', 'False'),
        # PBKDF2 costs ~3 s per check here: it dominates the suite runtime and makes a short
        # lockout window expire during the login it is supposed to block. Set E2E_REAL_HASHING=1
        # to exercise the production hasher instead.
        'INSECURE_FAST_PASSWORD_HASHING': '0' if os.environ.get('E2E_REAL_HASHING') == '1' else '1',
        'CLOUDGENE_E2E': '1',  # T09a core.checks.E001: required alongside the switch above
        'ALLOWED_HOSTS': '127.0.0.1,localhost',
        'CSRF_TRUSTED_ORIGINS': base_url,
        'PYTHONUNBUFFERED': '1',
        'PYTHONPATH': str(REPO) + os.pathsep + os.environ.get('PYTHONPATH', ''),
        'NXF_ANSI_LOG': 'false',
        'PATH': os.path.dirname(NEXTFLOW) + os.pathsep + os.environ.get('PATH', ''),
    })
    stack = Stack(name=name, root=root, base_url=base_url, env=env, home=home, outbox_dir=outbox,
                  db_path=db_path, log_dir=log_dir, pg_admin_url=E2E_DATABASE_URL, pg_db_name=pg_db_name)
    try:
        stack.manage('migrate', '--noinput', log_name='migrate.log')
        admin = constants.USERS['admin']
        stack.manage('create_admin', '--username', 'admin', '--email', admin['email'],
                     '--full-name', admin['full_name'], '--password', admin['password'],
                     log_name='create_admin.log')
        stack.run_seed('users')
        stack._spawn('server', ['runserver', '127.0.0.1:%d' % port, '--noreload', '--insecure'])
        stack.wait_ready()

        has_worker = stack.manage('help', 'run_worker', check=False).returncode == 0
        if has_worker:
            stack._spawn('worker', ['run_worker'])
            stack.worker_available = True
            stack.wait_worker_heartbeat()
        else:
            stack.worker_skip_reason = ('no `manage.py run_worker` command (needs T03): '
                                        'worker-dependent test skipped')
        stack.run_seed('workflows')
        db_summary = str(db_path) if db_path else 'postgres://%s:%s/%s' % (
            urlsplit(database_url).hostname, urlsplit(database_url).port or 5432, pg_db_name)
        (root / 'stack.json').write_text(json.dumps({
            'base_url': base_url, 'home': str(home), 'db': db_summary, 'outbox': str(outbox),
            'worker': stack.worker_available, 'health_endpoint': stack.health_endpoint}, indent=2))
    except BaseException:
        stack.stop()
        raise
    return stack
