"""
gunicorn config for the Cloudgene web process (TASKS T09a bullet 1).

Usage::

    gunicorn -c deploy/gunicorn.conf.py cloudgene_django.wsgi:application

Everything here is overridable by environment variable so the same file works across
environments; see deploy/cloudgene.env.example.
"""
import multiprocessing
import os


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')

# Sync workers (the default) are fine here: views are simple DB/file I/O, uploads are streamed
# to temp files by Django before the view runs, and the worker process (not gunicorn) runs
# Nextflow. CPU-bound Argon2/PBKDF2 hashing during login blocks one worker for ~0.1-0.3s; more
# workers cover that. Default: 2 * CPU + 1 (gunicorn's own rule of thumb), capped at 8 so a small
# host doesn't over-fork; override with GUNICORN_WORKERS.
workers = _int_env('GUNICORN_WORKERS', min(2 * multiprocessing.cpu_count() + 1, 8))
threads = _int_env('GUNICORN_THREADS', 1)
worker_class = os.environ.get('GUNICORN_WORKER_CLASS', 'sync')

# Large genomics inputs are uploaded as multipart/form-data and streamed to temp files by
# Django's upload handler while gunicorn reads the socket, but a slow client on a big body still
# needs headroom: keep the timeout well above the default 30s. server.max_upload_mb governs the
# real per-submission ceiling (jobs/submission.py); this is purely "don't kill a slow upload".
timeout = _int_env('GUNICORN_TIMEOUT', 300)
graceful_timeout = _int_env('GUNICORN_GRACEFUL_TIMEOUT', 30)
keepalive = _int_env('GUNICORN_KEEPALIVE', 5)

# nginx (deploy/nginx.conf.example) proxies from localhost; trust its X-Forwarded-* headers only
# from there unless GUNICORN_FORWARDED_ALLOW_IPS says otherwise (e.g. a container network CIDR).
forwarded_allow_ips = os.environ.get('GUNICORN_FORWARDED_ALLOW_IPS', '127.0.0.1')

accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')  # '-' = stdout (journald picks it up)
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# One worker restart per ~10k requests bounds any slow memory growth without a noticeable
# availability impact (gunicorn staggers restarts and the jitter avoids a thundering herd).
max_requests = _int_env('GUNICORN_MAX_REQUESTS', 10000)
max_requests_jitter = _int_env('GUNICORN_MAX_REQUESTS_JITTER', 500)

preload_app = os.environ.get('GUNICORN_PRELOAD_APP', '1') == '1'
