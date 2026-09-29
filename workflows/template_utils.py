"""
``CLOUDGENE_*`` variables available to Nextflow config/env files (SPEC W4).

The executor (T03) exports these into the Nextflow process environment, so
``nextflow.config`` can use ``"${CLOUDGENE_JOB_ID}"`` and ``nextflow.env`` can use
``$CLOUDGENE_SERVICE_NAME``. The admin UI lists :data:`VARIABLES` verbatim — keep this list,
:func:`cloudgene_variables` and SPEC §3.3 in sync.
"""
from core import config

# (name, scope, description). scope: global = any config, app/job = app & job configs only.
VARIABLES = [
    ('CLOUDGENE_SERVICE_NAME', 'global', 'Service name (server.name)'),
    ('CLOUDGENE_SERVICE_URL', 'global', 'Public base URL (server.url)'),
    ('CLOUDGENE_SMTP_HOST', 'global', 'SMTP host (mail.host)'),
    ('CLOUDGENE_SMTP_PORT', 'global', 'SMTP port (mail.port)'),
    ('CLOUDGENE_SMTP_USER', 'global', 'SMTP user (mail.user)'),
    ('CLOUDGENE_SMTP_PASSWORD', 'global', 'SMTP password (mail.password)'),
    ('CLOUDGENE_SMTP_SENDER', 'global', 'Sender address (mail.from_email)'),
    ('CLOUDGENE_WORKSPACE_TYPE', 'global', 'Workspace type (always "local")'),
    ('CLOUDGENE_WORKSPACE_HOME', 'global',
     'Directory holding all job workspaces; ${CLOUDGENE_WORKSPACE_HOME}/${CLOUDGENE_JOB_ID} is a job\'s workspace'),
    ('CLOUDGENE_APP_ID', 'app', 'Workflow id'),
    ('CLOUDGENE_APP_NAME', 'app', 'Workflow name'),
    ('CLOUDGENE_APP_VERSION', 'app', 'Workflow version'),
    ('CLOUDGENE_APP_LOCATION', 'app', 'Directory containing the cloudgene.yaml'),
    ('CLOUDGENE_JOB_ID', 'job', 'Job id (UUID)'),
    ('CLOUDGENE_JOB_NAME', 'job', 'Job name as entered by the user'),
    ('CLOUDGENE_JOB_LOCATION', 'job', 'The job workspace directory'),
    ('CLOUDGENE_JOB_SUBMITTED_ON', 'job', 'Submission time (ISO 8601)'),
    ('CLOUDGENE_USER_NAME', 'job', 'Username of the submitter'),
    ('CLOUDGENE_USER_EMAIL', 'job', 'E-mail of the submitter'),
    ('CLOUDGENE_USER_FULL_NAME', 'job', 'Full name of the submitter'),
]


def cloudgene_variables(workflow=None, job=None, user=None) -> dict:
    """Values for :data:`VARIABLES` (only the scopes for which objects are given)."""
    s = config.load_settings()
    out = {
        'CLOUDGENE_SERVICE_NAME': s['server']['name'],
        'CLOUDGENE_SERVICE_URL': s['server']['url'],
        'CLOUDGENE_SMTP_HOST': s['mail']['host'],
        'CLOUDGENE_SMTP_PORT': str(s['mail']['port']),
        'CLOUDGENE_SMTP_USER': s['mail']['user'],
        'CLOUDGENE_SMTP_PASSWORD': s['mail']['password'],
        'CLOUDGENE_SMTP_SENDER': s['mail']['from_email'],
        'CLOUDGENE_WORKSPACE_TYPE': 'local',
        'CLOUDGENE_WORKSPACE_HOME': str(config.jobs_dir()),
    }
    if workflow is not None:
        out.update({
            'CLOUDGENE_APP_ID': workflow.id,
            'CLOUDGENE_APP_NAME': workflow.name,
            'CLOUDGENE_APP_VERSION': workflow.version or '',
            'CLOUDGENE_APP_LOCATION': getattr(workflow, 'app_location', '') or '',
        })
    if job is not None:
        out.update({
            'CLOUDGENE_JOB_ID': str(job.id), 'CLOUDGENE_JOB_NAME': job.name or '',
            'CLOUDGENE_JOB_LOCATION': str(config.job_dir(job.id)),
            'CLOUDGENE_JOB_SUBMITTED_ON': job.submitted_at.isoformat() if job.submitted_at else '',
        })
        user = user or getattr(job, 'user', None)
    if user is not None:
        out.update({
            'CLOUDGENE_USER_NAME': user.username,
            'CLOUDGENE_USER_EMAIL': user.email or '',
            'CLOUDGENE_USER_FULL_NAME': getattr(user, 'full_name', '') or '',
        })
    return out
