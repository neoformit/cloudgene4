"""Arrange/assert helpers for the admin-panel scenarios (T05): settings.yaml, pages, jobs in DB."""
import json
import time

SPEC_TO_LEGACY = {'waiting': 'pending', 'success': 'completed'}


def create_jobs(stack, specs):
    """Insert jobs directly (no worker needed). specs: [(username, workflow_id, state, name)].

    Works before and after T03's state rename (field `state` or legacy `status`).
    Returns the job ids in order.
    """
    code = '''
import json
from django.contrib.auth import get_user_model
from jobs.models import Job
from workflows.models import Workflow
names = {f.name for f in Job._meta.get_fields()}
field = 'state' if 'state' in names else 'status'
legacy = %r if field == 'status' else {}
ids = []
for username, wf, state, name in json.loads(%r):
    job = Job.objects.create(user=get_user_model().objects.get(username=username),
                             workflow=Workflow.objects.get(pk=wf), name=name,
                             **{field: legacy.get(state, state)})
    ids.append(str(job.pk))
print(json.dumps(ids))
''' % (SPEC_TO_LEGACY, json.dumps(specs))
    return json.loads(stack.django_shell(code).strip().splitlines()[-1])


def delete_jobs(stack, ids):
    stack.django_shell('from jobs.models import Job; Job.objects.filter(pk__in=%r).delete()' % list(ids))


def job_state_counts(stack):
    code = '''
import json
from django.db.models import Count
from jobs.models import Job
names = {f.name for f in Job._meta.get_fields()}
field = 'state' if 'state' in names else 'status'
m = %r
out = {}
for v, n in Job.objects.values_list(field).annotate(n=Count('pk')).order_by():
    k = m.get(v, v)
    out[k] = out.get(k, 0) + n
print(json.dumps(out))
''' % {v: k for k, v in SPEC_TO_LEGACY.items()}
    return json.loads(stack.django_shell(code).strip().splitlines()[-1])


def wait_until(predicate, timeout=10, what='condition'):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(0.2)
    raise AssertionError('timed out waiting for %s (last: %r)' % (what, last))
