"""Arrange/assert helpers for the admin-panel scenarios (T05): settings.yaml, pages, jobs in DB."""
import json
import time

# Legacy values that may still sit in an old database (jobs migration 0003 renames them).
LEGACY_TO_SPEC = {'pending': 'waiting', 'completed': 'success'}


def create_jobs(stack, specs):
    """Insert jobs directly (no worker needed). specs: [(username, workflow_id, state, name)].

    States are the SPEC names (`waiting/running/success/failed/cancelled`), stored in
    `Job.status`. Returns the job ids in order.
    """
    code = '''
import json
from django.contrib.auth import get_user_model
from jobs.models import Job
from workflows.models import Workflow
names = {f.name for f in Job._meta.get_fields()}
field = 'state' if 'state' in names else 'status'
snapshot = {'app_id', 'app_name', 'workflow_yaml'} & names
ids = []
for username, wf, state, name in json.loads(%r):
    workflow = Workflow.objects.get(pk=wf)
    extra = {}
    if snapshot:
        extra = {'app_id': workflow.id, 'app_name': workflow.name,
                 'app_version': workflow.version, 'workflow_yaml': workflow.yaml_config}
    job = Job.objects.create(user=get_user_model().objects.get(username=username),
                             workflow=workflow, name=name, **{field: state}, **extra)
    ids.append(str(job.pk))
print(json.dumps(ids))
''' % json.dumps(specs)
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
''' % LEGACY_TO_SPEC
    return json.loads(stack.django_shell(code).strip().splitlines()[-1])


def db_counts(stack):
    """(users, enabled workflows) straight from the DB — other tests add users/workflows."""
    code = ('import json\n'
            'from django.contrib.auth import get_user_model\n'
            'from workflows.models import Workflow\n'
            'print(json.dumps([get_user_model().objects.count(),\n'
            '                  Workflow.objects.filter(status="enabled").count()]))')
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
