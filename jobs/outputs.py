"""
Job outputs: collection into ``JobOutput`` rows and safe resolution for downloads/logs.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from core import config as cloudgene_config
from workflows.definition import WorkflowDefinition

from .models import Job, JobOutput

MAX_FILES_PER_OUTPUT = 5000
LOG_TAIL_BYTES = 256 * 1024


def _allowed_roots(job: Job) -> list[Path]:
    """The job's own workspace, plus its actual Nextflow work dir.

    A-04: this must resolve the work dir exactly like ``jobs.runner.work_dir_for`` (per-app
    ``apps[].work_dir`` first, else the global ``nextflow.work_dir``), or a per-app override
    is honoured by the runner but not here — every published (symlinked) output then resolves
    outside every allowed root and is silently dropped by ``collect_outputs``/
    ``resolve_output_file``.
    """
    from . import runner, workflow_bridge  # local import: runner/workflow_bridge don't import us

    roots = [cloudgene_config.job_dir(job.id).resolve()]
    configured = (workflow_bridge.nextflow_work_dir(job.workflow) if job.workflow_id
                 else (cloudgene_config.get('nextflow.work_dir', '') or '').strip())
    roots.append(runner.work_dir_for(job, configured).resolve())
    return roots


def _within(path: Path, roots) -> bool:
    return any(path == root or root in path.parents for root in roots)


def safe_relative(rel: str) -> PurePosixPath | None:
    """Lexically validate a relative path: no absolute paths, no ``..``, no empty parts."""
    if not rel or '\x00' in rel or rel.startswith(('/', '\\')):
        return None
    p = PurePosixPath(rel.replace('\\', '/'))
    if any(part in ('..', '.', '') for part in p.parts) or p.is_absolute():
        return None
    return p


def resolve_output_file(job: Job, output: JobOutput) -> Path | None:
    """Absolute path of a JobOutput file, or None if missing / outside the job's roots.
    Symlinks (Nextflow ``publishDir`` default) may point into the job's work dir only."""
    rel = safe_relative(output.path)
    if rel is None:
        return None
    output_dir = cloudgene_config.job_dir(job.id) / 'output'
    candidate = output_dir.joinpath(*rel.parts)
    try:
        real = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not real.is_file() or not _within(real, _allowed_roots(job)):
        return None
    return real


def collect_outputs(job: Job, definition: WorkflowDefinition) -> list[JobOutput]:
    """Replace the job's JobOutput rows with the files currently under ``output/<id>``
    for every output with ``download: true``."""
    output_dir = cloudgene_config.job_dir(job.id) / 'output'
    roots = _allowed_roots(job)
    rows = []
    for out in definition.outputs:
        if not out.download:
            continue
        base = output_dir / out.id
        files = []
        if base.is_file() or (base.is_symlink() and not base.is_dir()):
            files = [base]
        elif base.is_dir():
            for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
                dirnames.sort()
                for fn in sorted(filenames):
                    files.append(Path(dirpath) / fn)
                    if len(files) >= MAX_FILES_PER_OUTPUT:
                        break
        for f in files:
            try:
                real = f.resolve(strict=True)
            except (OSError, RuntimeError):
                continue
            if not real.is_file() or not _within(real, roots):
                continue
            rows.append(JobOutput(
                job=job, output_id=out.id, label=out.label,
                path=f.relative_to(output_dir).as_posix(), size=real.stat().st_size,
            ))
    JobOutput.objects.filter(job=job).delete()
    JobOutput.objects.bulk_create(rows)
    return rows


def read_job_log(job: Job) -> str:
    """Combined job log: worker/stdout log + tail of every nextflow.log."""
    logs = cloudgene_config.job_dir(job.id) / 'logs'
    parts = []
    stdout = logs / 'stdout.txt'
    if stdout.is_file():
        parts.append(_tail(stdout))
    for log in sorted(logs.glob('*nextflow.log')):
        parts.append(f'\n===== {log.name} (tail) =====\n' + _tail(log))
    if not parts:
        if job.error_message:
            return job.error_message + '\n'
        return 'No log available yet.\n' if job.is_active else 'No log available.\n'
    return ''.join(parts)


def _tail(path: Path, limit=LOG_TAIL_BYTES) -> str:
    try:
        size = path.stat().st_size
        with open(path, 'rb') as fh:
            if size > limit:
                fh.seek(size - limit)
                data = fh.read()
                data = data[data.find(b'\n') + 1:]
                return f'[... {size - limit} bytes omitted ...]\n' + data.decode('utf-8', 'replace')
            return fh.read().decode('utf-8', 'replace')
    except OSError:
        return ''
