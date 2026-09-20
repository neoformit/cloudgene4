"""X1 (jobs part): bob opens alice's job page, output URL and log URL → 404, no content leaks."""
import pytest
from playwright.sync_api import expect

from e2e.helpers import wait_job_state


@pytest.fixture(scope='module')
def alice_job(stack, api_module):
    stack.require_worker()
    alice = api_module('alice')
    job = alice.submit_job('hello', name='X1 private job', params={'message': 'top secret ✓'})
    detail = wait_job_state(alice, job['id'], 'success', timeout=150)
    detail = alice.get_job(job['id'])
    return detail


@pytest.fixture(scope='module')
def api_module(stack):
    from e2e.helpers import ApiClient
    clients = []

    def _api(user):
        c = ApiClient(stack.base_url)
        c.login(user)
        clients.append(c)
        return c
    yield _api
    for c in clients:
        c.close()


@pytest.mark.worker
def test_other_user_cannot_see_job_outputs_or_log(page, login, api_module, alice_job, expect_api_error):
    job_id = alice_job['id']
    output_url = alice_job['outputs'][0]['url']
    bob = api_module('bob')
    for url in ('/api/jobs/%s/' % job_id, '/api/jobs/%s/status/' % job_id, output_url,
                '/api/jobs/%s/log/' % job_id):
        r = bob.get(url)
        assert r.status_code == 404, (url, r.status_code)
        assert b'top secret' not in r.content
    assert bob.post('/api/jobs/%s/cancel/' % job_id).status_code == 404
    assert bob.delete('/api/jobs/%s/' % job_id).status_code == 404
    assert all(j['id'] != job_id for j in bob.get_json('/api/jobs/')['results'])

    login(page, 'bob')
    expect_api_error(404, '/api/jobs/*')
    page.goto('/jobs/%s' % job_id)
    expect(page.get_by_test_id('job-error')).to_contain_text('not found')
    expect(page.get_by_test_id('job-title')).to_have_count(0)


@pytest.mark.worker
def test_anonymous_cannot_download(stack, alice_job):
    import requests
    r = requests.get(stack.base_url + alice_job['outputs'][0]['url'], timeout=10)
    assert r.status_code == 401
    assert b'top secret' not in r.content


@pytest.mark.worker
def test_owner_and_admin_can_download(api_module, alice_job):
    url = alice_job['outputs'][0]['url']
    assert api_module('alice').get(url).content == 'top secret ✓\n'.encode()
    assert api_module('admin').get(url).status_code == 200
