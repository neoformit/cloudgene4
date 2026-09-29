"""``type: command`` steps (T10): variable substitution/quoting (pure) and the worker lifecycle."""
import json
import os
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase

from core import config as cloudgene_config
from jobs import stepvars
from jobs import worker as worker_mod
from jobs.models import Job, JobOutput, JobState
from workflows.definition import parse_definition

from .helpers import make_app, pid_alive
from .test_worker import WorkerTestBase

INJECTIONS = ['x; touch /tmp/pwned', '$(id)', '`id`', "it's \"quoted\" $HOME \\ back", 'a b\tc\nd',
              '*', '--flag', '', '${CLOUDGENE_JOB_ID}']


def run_bash(script):
    return subprocess.run(['/bin/bash', '-c', script], capture_output=True, text=True, check=True,
                          env={'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent-home'}).stdout


class SubstitutionTest(SimpleTestCase):
    def test_argv_mode_splits_template_before_substituting(self):
        for value in INJECTIONS:
            argv = stepvars.split_command("/bin/echo --a=$x '$x' \"${x}\" $y $z ${x}${x}",
                                          {'x': value, 'y': 'Y'})
            self.assertEqual(argv, ['/bin/echo', f'--a={value}', value, value, 'Y', '$z', value + value])

    def test_argv_mode_value_with_spaces_stays_one_token(self):
        self.assertEqual(stepvars.split_command('/bin/echo $x', {'x': 'x; touch /tmp/pwned'}),
                         ['/bin/echo', 'x; touch /tmp/pwned'])

    def test_bash_mode_values_are_literal_in_every_quote_context(self):
        for value in INJECTIONS:
            template = ("printf '%s|' $x; printf '%s|' \"$x\"; printf '%s|' \"pre-${x}-post\"; "
                        "printf '%s|' '$x'; printf '%s|' pre$x")
            script = stepvars.quote_into_shell(template, {'x': value})
            expected = f'{value}|{value}|pre-{value}-post|{value}|pre{value}|'
            if value == '':
                expected = '|' + '|' + 'pre--post|' + '|' + 'pre|'
                # `printf '%s|' $x` with an empty *quoted* word still prints one empty field
            self.assertEqual(run_bash(script), expected, (value, script))

    def test_bash_mode_never_runs_injected_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in (f'x; touch {tmp}/pwned', f'$(touch {tmp}/pwned)', f'`touch {tmp}/pwned`',
                          f'x && touch {tmp}/pwned', f'x | touch {tmp}/pwned'):
                script = stepvars.quote_into_shell('echo $v "$v" \'$v\'', {'v': value})
                self.assertEqual(run_bash(script), f'{value} {value} {value}\n')
            self.assertEqual(os.listdir(tmp), [])

    def test_bash_mode_pipeline_from_taxodactyl(self):
        template = ("/usr/bin/grep 'Azure Key Vault:' $outdir/run.log | /usr/bin/sed "
                    "'s/^.* - DEBUG - //' | /usr/bin/sort -u")
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp) / 'out dir; x'
            outdir.mkdir()
            (outdir / 'run.log').write_text('1 - DEBUG - Azure Key Vault: b\n2 - DEBUG - Azure Key Vault: a\n'
                                            '3 - DEBUG - Azure Key Vault: a\nother\n')
            script = stepvars.quote_into_shell(template, {'outdir': str(outdir)})
            self.assertEqual(run_bash(script), 'Azure Key Vault: a\nAzure Key Vault: b\n')

    def test_unknown_and_non_identifier_dollars_are_left_alone(self):
        variables = {'x': '1'}
        self.assertEqual(stepvars.substitute('$x $nope ${nope} $1 $$ ${x:-d} $(x) $', variables),
                         '1 $nope ${nope} $1 $$ ${x:-d} $(x) $')
        script = stepvars.quote_into_shell('echo $HOME ${FOO:-dflt} $x', variables)
        self.assertEqual(run_bash(script), '/nonexistent-home dflt 1\n')

    def test_values_are_not_rescanned(self):
        self.assertEqual(stepvars.substitute('$a', {'a': '$b', 'b': 'X'}), '$b')

    def test_backslash_escaped_dollar_is_left_to_the_shell(self):
        self.assertEqual(run_bash(stepvars.quote_into_shell(r'echo \$x $x', {'x': 'v'})), '$x v\n')

    def test_params_substitution_is_recursive_and_only_touches_strings(self):
        out = stepvars.substitute_params(
            {'a': '${p}/x', 'n': 3, 'l': ['$p', 1], 'd': {'k': '$q'}}, {'p': '/w', 'q': 'Q'})
        self.assertEqual(out, {'a': '/w/x', 'n': 3, 'l': ['/w', 1], 'd': {'k': 'Q'}})

    def test_build_variables(self):
        definition = parse_definition({
            'id': 'a', 'name': 'A', 'workflow': {
                'steps': [{'name': 'S', 'script': 'main.nf'}],
                'inputs': [
                    {'id': 'f', 'type': 'file'}, {'id': 'd', 'type': 'folder'},
                    {'id': 's', 'type': 'string'}, {'id': 'n', 'type': 'number'},
                    {'id': 'c', 'type': 'checkbox'}, {'id': 'opt', 'type': 'string', 'required': False},
                    {'id': 'ta', 'type': 'textarea', 'writeFile': 'x.txt'}, {'id': 'sep', 'type': 'separator'}],
                'outputs': [{'id': 'outdir', 'type': 'folder'}]}})
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp).resolve() / 'job'
            v = stepvars.build_variables(
                definition,
                {'f': 'input/f/a b.csv', 'd': 'input/d', 's': 'hi', 'n': 2.5, 'c': True,
                 'ta': 'input/ta/x.txt'},
                job_dir, {'CLOUDGENE_JOB_ID': 'J', 'PATH': '/bin', 'CLOUDGENE_WORKSPACE_HOME': '/w'})
        self.assertEqual(v['f'], str(job_dir / 'input/f/a b.csv'))
        self.assertEqual(v['d'], str(job_dir / 'input/d'))
        self.assertEqual((v['s'], v['n'], v['c'], v['opt']), ('hi', '2.5', 'true', ''))
        self.assertEqual(v['ta'], str(job_dir / 'input/ta/x.txt'))
        self.assertEqual(v['outdir'], str(job_dir / 'output' / 'outdir'))
        self.assertEqual((v['CLOUDGENE_JOB_ID'], v['CLOUDGENE_WORKSPACE_HOME']), ('J', '/w'))
        self.assertNotIn('PATH', v)
        self.assertNotIn('sep', v)


APP_YAML = """
id: cmd
name: Cmd
version: 2.0.0
workflow:
  steps:
    - name: Pipeline
      params:
        fake_tasks: 1
        trace_file: ${CLOUDGENE_WORKSPACE_HOME}/${CLOUDGENE_JOB_ID}/logs/step1-trace.csv
        who: ${CLOUDGENE_USER_EMAIL} / ${CLOUDGENE_USER_FULL_NAME}
        tmp: ./tmp
        title_copy: $title
      stdout: true
      stderr: true
    - name: Say
      type: command
      cmd: /usr/bin/env bash ${CLOUDGENE_APP_LOCATION}/bin/say.sh --dir $outdir --title $title
      stdout: true
      stderr: true
    - name: Pipe
      type: command
      cmd: >
        /bin/cat $outdir/result.txt
        | /bin/sed 's/^name=/piped:/'
      bash: true
      stdout: true
    - name: Quiet
      type: command
      cmd: /usr/bin/env bash ${CLOUDGENE_APP_LOCATION}/bin/quiet.sh $outdir
    - name: Zip
      type: command
      cmd: /usr/bin/env bash ${CLOUDGENE_APP_LOCATION}/bin/zip.sh $outdir
  inputs:
    - id: title
      description: Title
      type: text
      required: false
  outputs:
    - id: outdir
      description: Results
      type: folder
"""

FILES = {
    'bin/say.sh': textwrap.dedent("""\
        echo "say: dir=$2 title=[$4] cwd=$(pwd) job=$CLOUDGENE_JOB_ID"
        echo "say-warning" >&2
        """),
    'bin/quiet.sh': 'echo hidden-stdout; echo hidden-stderr >&2\n',
    'bin/zip.sh': 'cd "$1" && python3 -c "import zipfile; z=zipfile.ZipFile(\'reports.zip\',\'w\'); z.write(\'result.txt\'); z.close()"\n',
}


class CommandStepWorkerTest(WorkerTestBase):
    def run_job(self, yaml_text=APP_YAML, files=FILES, app='cmd', **data):
        make_app(app, yaml_text, files=files)
        job = self.submit(app, **data)
        self.worker.drain(timeout=60, tick_seconds=0.05)
        job.refresh_from_db()
        return job

    def test_taxodactyl_shaped_job(self):
        job = self.run_job(title='hello world')
        self.assertEqual(job.status, JobState.SUCCESS, job.error_message)
        self.assertEqual(list(job.steps.values_list('name', 'status')),
                         [(n, 'success') for n in ('Pipeline', 'Say', 'Pipe', 'Quiet', 'Zip')])
        workspace = cloudgene_config.job_dir(job.id)
        outdir = (workspace / 'output' / 'outdir').resolve()

        # Nextflow params: variables substituted, relative values untouched
        inv = json.loads((workspace / 'work' / 'invocation.json').read_text())
        self.assertEqual(inv['params']['trace_file'], f'{workspace.parent}/{job.id}/logs/step1-trace.csv')
        self.assertEqual(inv['params']['who'], 'alice@example.com / Alice Tester')
        self.assertEqual(inv['params']['tmp'], './tmp')
        self.assertEqual(inv['params']['title_copy'], 'hello world')
        self.assertEqual(inv['env']['CLOUDGENE_WORKSPACE_HOME'], str(cloudgene_config.jobs_dir()))

        messages = list(job.messages.values_list('level', 'text'))
        say = next(t for lvl, t in messages if t.startswith('say: '))
        self.assertEqual(say, f'say: dir={outdir} title=[hello world] cwd={workspace} job={job.id}')
        self.assertIn(('warning', 'say-warning'), messages)
        self.assertIn(('info', 'piped:hello world'), messages)      # $outdir/result.txt from step 1
        self.assertNotIn('hidden', ' '.join(t for _, t in messages))
        # the unflagged streams are still in the step's own log files
        logs = workspace / 'logs'
        self.assertEqual((logs / 'step4-command.stdout.txt').read_text(), 'hidden-stdout\n')
        self.assertEqual((logs / 'step4-command.stderr.txt').read_text(), 'hidden-stderr\n')
        from jobs.outputs import read_job_log
        log = read_job_log(job)
        self.assertIn('say-warning', log)
        self.assertNotIn('hidden-stdout', log)

        paths = sorted(JobOutput.objects.filter(job=job).values_list('path', flat=True))
        self.assertEqual(paths, ['outdir/reports.zip', 'outdir/result.txt', 'outdir/sub dir/nested ü.txt'])

    def test_injection_is_literal_in_both_modes(self):
        yaml_text = textwrap.dedent("""
            id: inj
            name: Inj
            workflow:
              steps:
                - {name: Argv, type: command, cmd: "/bin/echo [$title]", stdout: true}
                - {name: Shell, type: command, cmd: "echo [$title] \\"[$title]\\"", bash: true, stdout: true}
              inputs:
                - {id: title, type: text, required: false}
              outputs:
                - {id: outdir, type: folder}
        """)
        with tempfile.TemporaryDirectory() as tmp:
            for value in (f'x; touch {tmp}/pwned', f'$(touch {tmp}/pwned)', f"a'b\"c `touch {tmp}/pwned`"):
                make_app('inj', yaml_text, files={})
                job = self.submit('inj', title=value)
                self.worker.drain(timeout=60, tick_seconds=0.05)
                job.refresh_from_db()
                self.assertEqual(job.status, JobState.SUCCESS, job.error_message)
                texts = [t for lvl, t in job.messages.values_list('level', 'text') if t.startswith('[')]
                self.assertEqual(texts, [f'[{value}]', f'[{value}] [{value}]'])
                self.assertEqual(os.listdir(tmp), [])

    def test_failing_command_fails_job_with_exit_code_and_stderr_tail(self):
        yaml_text = textwrap.dedent("""
            id: bad
            name: Bad
            workflow:
              steps:
                - {name: Boom, type: command, cmd: "echo out; echo 'it broke badly' >&2; exit 3", bash: true, stdout: true}
                - {name: Never, type: command, cmd: "/usr/bin/touch $outdir/never"}
              outputs:
                - {id: outdir, type: folder}
        """)
        make_app('bad', yaml_text, files={})
        job = self.submit('bad')
        self.worker.drain(timeout=30, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.FAILED)
        self.assertIn('Boom', job.error_message)
        self.assertIn('failed (exit code 3)', job.error_message)
        self.assertNotIn('it broke badly', job.error_message)   # stderr flag is off
        self.assertEqual(list(job.steps.values_list('status', flat=True)), ['failed', 'cancelled'])
        self.assertIn(('info', 'out'), job.messages.values_list('level', 'text'))
        self.assertFalse((cloudgene_config.job_dir(job.id) / 'output' / 'outdir' / 'never').exists())

    def test_missing_executable(self):
        yaml_text = 'id: nx\nname: N\nworkflow:\n  steps:\n    - {name: X, type: command, cmd: /no/such/tool --x}\n'
        make_app('nx', yaml_text, files={})
        job = self.submit('nx')
        self.worker.drain(timeout=30, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.FAILED)
        self.assertIn('/no/such/tool', job.error_message)

    def test_cancel_during_long_command_kills_the_process_group(self):
        yaml_text = textwrap.dedent("""
            id: sleepy
            name: Sleepy
            workflow:
              steps:
                - {name: Zzz, type: command, cmd: "sleep 300 & echo $! > $outdir/child.pid; wait", bash: true}
              outputs:
                - {id: outdir, type: folder}
        """)
        make_app('sleepy', yaml_text, files={})
        job = self.submit('sleepy')
        pidfile = cloudgene_config.job_dir(job.id) / 'output' / 'outdir' / 'child.pid'
        self.run_until(lambda: pidfile.exists() and pidfile.read_text().strip())
        child = int(pidfile.read_text())
        self.assertTrue(pid_alive(child))
        Job.objects.filter(pk=job.pk).update(cancel_requested=True)
        self.run_until(lambda: self.state(job) == JobState.CANCELLED, timeout=30)
        deadline = time.monotonic() + 10
        while pid_alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(pid_alive(child))
        self.assertEqual(job.steps.get().status, 'cancelled')

    def test_runaway_output_is_capped(self):
        yaml_text = textwrap.dedent("""
            id: loud
            name: Loud
            workflow:
              steps:
                - {name: Loud, type: command, cmd: "yes", stdout: true}
        """)
        make_app('loud', yaml_text, files={})
        with mock.patch.object(worker_mod, 'COMMAND_OUTPUT_LIMIT', 200_000):
            job = self.submit('loud')
            self.worker.drain(timeout=60, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.FAILED)
        self.assertIn('output exceeded', job.error_message)
        for _, text in job.messages.values_list('level', 'text'):
            self.assertLess(len(text), worker_mod.COMMAND_MESSAGE_BYTES + 200)
        self.assertLess((cloudgene_config.job_dir(job.id) / 'logs' / 'stdout.txt').stat().st_size,
                        worker_mod.COMMAND_LOG_BYTES + 4096)

    def test_nextflow_stdout_flag_adds_output_to_failure_message(self):
        yaml_text = textwrap.dedent("""
            id: nf
            name: NF
            workflow:
              steps:
                - {name: P, params: {fake_mode: fail}, stdout: true}
        """)
        make_app('nf', yaml_text, files={})
        job = self.submit('nf')
        self.worker.drain(timeout=30, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertIn('Output (last lines):', job.error_message)
        self.assertIn('plain output line', job.error_message)
        make_app('nf2', yaml_text.replace('id: nf', 'id: nf2').replace('stdout: true', 'stdout: false'),
                 files={})
        job2 = self.submit('nf2')
        self.worker.drain(timeout=30, tick_seconds=0.05)
        job2.refresh_from_db()
        self.assertNotIn('Output (last lines):', job2.error_message)


class StreamVisibilityTest(WorkerTestBase):
    """A stream whose flag is false must not reach anything the owner can see (only the step's
    log file on disk); with the flag true it is shown (T10 follow-up)."""
    SECRET = 'SECRET-TOKEN-hunter2'   # assembled by the shell so the command line itself does not contain it

    def run_failing(self, stream, flag):
        cmd = f"p=SECRET-TOKEN; echo $p-hunter2 {'>&2' if stream == 'stderr' else ''}; exit 1"
        yaml_text = textwrap.dedent(f"""
            id: vis
            name: Vis
            workflow:
              steps:
                - name: Leaky
                  type: command
                  bash: true
                  cmd: "{cmd}"
                  {stream}: {'true' if flag else 'false'}
        """)
        make_app('vis', yaml_text, files={})
        job = self.submit('vis')
        self.worker.drain(timeout=30, tick_seconds=0.05)
        job.refresh_from_db()
        self.assertEqual(job.status, JobState.FAILED)
        return job

    def visible(self, job):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(self.user)
        parts = []
        for path in ('', 'status/', 'log/'):
            r = client.get(f'/api/jobs/{job.id}/{path}')
            self.assertEqual(r.status_code, 200, path)
            parts.append(r.content.decode())
        r = client.get('/api/jobs/')
        parts.append(r.content.decode())
        return '\n'.join(parts)

    def test_hidden_streams_stay_on_disk(self):
        for stream in ('stderr', 'stdout'):
            with self.subTest(stream=stream):
                job = self.run_failing(stream, False)
                self.assertIn('failed (exit code 1)', job.error_message)
                self.assertNotIn(self.SECRET, self.visible(job))
                disk = cloudgene_config.job_dir(job.id) / 'logs' / f'step1-command.{stream}.txt'
                self.assertIn(self.SECRET, disk.read_text())

    def test_flagged_streams_are_shown(self):
        for stream in ('stderr', 'stdout'):
            with self.subTest(stream=stream):
                job = self.run_failing(stream, True)
                self.assertIn(self.SECRET, self.visible(job))
                self.assertIn('failed (exit code 1)', job.error_message)
                self.assertIn(self.SECRET, job.error_message)
