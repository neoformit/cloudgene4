"""Unit tests for workflows.definition (SPEC §4)."""
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from workflows.definition import DefinitionError, load_definition, parse_definition

ALL_INPUTS = """
id: all-inputs
name: All inputs
version: 1.2.3
description: <b>demo</b>
author: Me
category: test
workflow:
  steps:
    - name: Run
      script: main.nf
      revision: '1.0'
      params: {fixed: 1}
      processes:
        - process: SAY
          label: Saying
          view: progressbar
  inputs:
    - id: title
      description: Title
      type: text
      value: hi there
    - id: sep
      type: separator
    - id: count
      description: Count
      type: number
      value: 3
      min: 1
      max: 10
    - id: notes
      description: Notes
      type: textarea
      writeFile: notes.txt
      required: false
    - id: mode
      description: Mode
      type: list
      value: fast
      values:
        fast: Fast mode
        slow: Slow mode
    - id: flavour
      description: Flavour
      type: radio
      values: [a, b]
    - id: flag
      description: Flag
      type: checkbox
      value: true
      values:
        true: yes-please
        false: no-thanks
    - id: plain_flag
      description: Plain
      type: checkbox
    - id: data
      description: Data
      type: file
      accept: .csv, .vcf.gz, text/plain
    - id: many
      description: Many
      type: folder
      required: false
    - id: hidden
      description: Hidden
      type: text
      visible: false
      value: secret
    - id: terms
      description: I agree
      type: terms_checkbox
  outputs:
    - id: outdir
      description: Results
      type: folder
    - id: report
      description: Report
      type: file
      download: false
"""


class LoadDefinitionTest(SimpleTestCase):
    def test_all_input_types(self):
        d = load_definition(ALL_INPUTS)
        self.assertEqual((d.id, d.name, d.version, d.author, d.category),
                         ('all-inputs', 'All inputs', '1.2.3', 'Me', 'test'))
        self.assertEqual(len(d.inputs), 12)
        self.assertEqual(d.input('title').value, 'hi there')
        count = d.input('count')
        self.assertEqual((count.value, count.min, count.max), (3, 1, 10))
        self.assertEqual(d.input('notes').write_file, 'notes.txt')
        self.assertFalse(d.input('notes').required)
        self.assertEqual(d.input('mode').values,
                         [{'key': 'fast', 'label': 'Fast mode'}, {'key': 'slow', 'label': 'Slow mode'}])
        self.assertEqual(d.input('flavour').value_keys, ['a', 'b'])
        flag = d.input('flag')
        self.assertIs(flag.value, True)
        self.assertEqual(flag.checkbox_values, {'true': 'yes-please', 'false': 'no-thanks'})
        self.assertFalse(flag.required)
        self.assertIs(d.input('plain_flag').value, False)
        self.assertEqual(d.input('data').accept_extensions, ['.csv', '.vcf.gz'])
        self.assertTrue(d.input('many').is_folder)
        self.assertFalse(d.input('hidden').visible)
        self.assertTrue(d.input('terms').is_terms)
        self.assertTrue(d.input('sep').is_display)
        self.assertNotIn('sep', [p.id for p in d.value_inputs])
        self.assertEqual([o.id for o in d.outputs], ['outdir', 'report'])
        self.assertTrue(d.output('outdir').download)
        self.assertFalse(d.output('report').download)
        step = d.steps[0]
        self.assertEqual((step.type, step.script, step.revision, step.params),
                         ('nextflow', 'main.nf', '1.0', {'fixed': 1}))
        self.assertEqual(step.processes[0]['label'], 'Saying')
        self.assertEqual(d.to_dict()['inputs'][0]['id'], 'title')

    def test_load_from_dir_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'cloudgene.yaml').write_text(ALL_INPUTS)
            d = load_definition(Path(tmp))
            self.assertEqual(d.app_dir, Path(tmp))
            self.assertEqual(d.yaml_text, ALL_INPUTS)
            d2 = load_definition(str(Path(tmp) / 'cloudgene.yaml'))
            self.assertEqual(d2.id, 'all-inputs')
            with self.assertRaises(DefinitionError):
                load_definition(Path(tmp) / 'missing')

    def test_missing_path_string(self):
        with self.assertRaises(DefinitionError) as cm:
            load_definition('/nonexistent/app')
        self.assertIn('not found', str(cm.exception))

    def test_required_fields(self):
        with self.assertRaises(DefinitionError) as cm:
            parse_definition({'workflow': {'steps': []}})
        errors = cm.exception.errors
        self.assertIn('id: is required', errors)
        self.assertIn('name: is required', errors)
        self.assertTrue(any('workflow.steps' in e for e in errors))

    def test_invalid_yaml(self):
        with self.assertRaises(DefinitionError):
            load_definition('id: [unclosed\nname: x')

    def test_unknown_input_type(self):
        with self.assertRaises(DefinitionError) as cm:
            load_definition('id: a\nname: A\nworkflow:\n  steps: [{script: main.nf}]\n'
                            '  inputs:\n    - {id: x, type: app_list}\n')
        self.assertIn('workflow.inputs[0].type', cm.exception.errors[0])

    def test_invalid_ids_and_duplicates(self):
        yaml_text = ('id: Bad Id\nname: A\nworkflow:\n  steps: [{script: main.nf}]\n'
                     '  inputs:\n    - {id: "a b", type: text}\n    - {id: workflow, type: text}\n'
                     '    - {id: x, type: text}\n  outputs:\n    - {id: x, type: folder}\n')
        with self.assertRaises(DefinitionError) as cm:
            load_definition(yaml_text)
        text = ' | '.join(cm.exception.errors)
        self.assertIn('id: "Bad Id"', text)
        self.assertIn('"a b"', text)
        self.assertIn('reserved', text)
        self.assertIn('duplicate id "x"', text)

    def test_list_needs_values_and_number_bounds(self):
        yaml_text = ('id: a\nname: A\nworkflow:\n  steps: [{script: main.nf}]\n  inputs:\n'
                     '    - {id: l, type: list}\n    - {id: n, type: number, min: 5, max: 1}\n'
                     '    - {id: m, type: number, min: abc}\n'
                     '    - {id: c, type: checkbox, values: {true: x}}\n'
                     '    - {id: t, type: text, writeFile: out.txt}\n')
        with self.assertRaises(DefinitionError) as cm:
            load_definition(yaml_text)
        text = ' | '.join(cm.exception.errors)
        self.assertIn('inputs[0].values', text)
        self.assertIn('min must be <= max', text)
        self.assertIn('inputs[2].min: must be a number', text)
        self.assertIn('true and false', text)
        self.assertIn('only supported for textarea', text)

    def test_unsupported_steps_load_with_error(self):
        d = load_definition('id: a\nname: A\nworkflow:\n  steps:\n'
                            '    - {name: Java, classname: cloudgene.Foo}\n'
                            '    - {name: Groovy, type: groovy, script: x.groovy}\n'
                            '    - {name: Dock, type: docker, image: x}\n')
        self.assertEqual([s.type for s in d.steps], ['unsupported'] * 3)
        self.assertIn('classname', d.steps[0].error)
        self.assertEqual(len(d.warnings), 3)

    def test_default_script_is_main_nf(self):
        d = load_definition('id: a\nname: A\nworkflow:\n  steps:\n    - name: S\n      type: nextflow\n')
        self.assertEqual(d.steps[0].script, 'main.nf')

    def test_bad_default_for_list_is_ignored_with_warning(self):
        d = load_definition('id: a\nname: A\nworkflow:\n  steps: [{script: main.nf}]\n  inputs:\n'
                            '    - {id: l, type: list, value: zzz, values: {a: A}}\n')
        self.assertEqual(d.input('l').value, '')
        self.assertTrue(d.warnings)

    def test_checkbox_default_by_mapped_value(self):
        d = load_definition('id: a\nname: A\nworkflow:\n  steps: [{script: main.nf}]\n  inputs:\n'
                            '    - {id: c, type: checkbox, value: on-val, values: {true: on-val, false: off-val}}\n')
        self.assertIs(d.input('c').value, True)


class CommandStepParsingTest(SimpleTestCase):
    def wf(self, *steps):
        return 'id: a\nname: A\nworkflow:\n  steps:\n' + ''.join(steps)

    def test_command_step_keys(self):
        d = load_definition(self.wf(
            '    - {name: C, type: command, cmd: "/bin/echo $x", bash: true, stdout: true}\n'))
        step = d.steps[0]
        self.assertEqual((step.type, step.cmd, step.bash, step.stdout, step.stderr),
                         ('command', '/bin/echo $x', True, True, False))
        self.assertTrue(step.supported)
        self.assertEqual(d.warnings, [])

    def test_cmd_without_type_and_exec_alias(self):
        d = load_definition(self.wf('    - {name: A, cmd: /bin/true}\n',
                                    '    - {name: B, type: command, exec: /bin/false}\n'))
        self.assertEqual([(s.type, s.cmd) for s in d.steps],
                         [('command', '/bin/true'), ('command', '/bin/false')])

    def test_missing_or_empty_cmd_is_an_error(self):
        for body in ('{name: C, type: command}', '{name: C, type: command, cmd: ""}',
                     '{name: C, type: command, cmd: "  "}'):
            with self.assertRaises(DefinitionError) as cm:
                load_definition(self.wf(f'    - {body}\n'))
            self.assertIn('cmd', cm.exception.errors[0])

    def test_unbalanced_quotes_error_unless_bash(self):
        with self.assertRaises(DefinitionError):
            load_definition(self.wf('    - {name: C, type: command, cmd: "echo \'x"}\n'))
        load_definition(self.wf('    - {name: C, type: command, cmd: "echo \'x", bash: true}\n'))

    def test_bad_flags_are_errors(self):
        with self.assertRaises(DefinitionError):
            load_definition(self.wf('    - {name: C, type: command, cmd: x, stdout: maybe}\n'))

    def test_nextflow_step_with_stdout_flags(self):
        d = load_definition(self.wf('    - {name: N, stdout: true, stderr: true}\n'))
        self.assertEqual((d.steps[0].type, d.steps[0].script, d.steps[0].stdout, d.steps[0].stderr),
                         ('nextflow', 'main.nf', True, True))

    def test_taxodactyl_definition(self):
        path = Path(__file__).parent / 'fixtures' / 'taxodactyl-v1.5.0.yml'
        d = load_definition(path.read_text())
        self.assertEqual(d.warnings, [])
        self.assertEqual([s.type for s in d.steps], ['nextflow', 'command', 'command', 'command'])
        self.assertEqual(d.steps[0].script, 'main.nf')
        self.assertTrue(d.steps[0].stdout and d.steps[0].stderr)
        self.assertTrue(d.steps[1].bash)
        self.assertIn('$outdir/run.log', d.steps[1].cmd)
        self.assertFalse(d.steps[2].bash)
        self.assertEqual(d.steps[3].cmd,
                         '/usr/bin/bash ${CLOUDGENE_APP_LOCATION}/bin/zip_reports.sh --dir $outdir')
        self.assertEqual([p.id for p in d.inputs], ['metadata', 'sequences', 'ncbi_api_key', 'facility_name'])
        self.assertEqual(d.input('metadata').accept, '.csv')
        self.assertTrue(d.input('metadata').help.startswith('https://'))
        self.assertIn('Right click', d.input('metadata').details)
        self.assertFalse(d.input('sequences').required)
        self.assertEqual((d.author.split(',')[0], d.output('outdir').type), ('Magdalena Antczak', 'folder'))
        self.assertTrue(d.logo.startswith('https://'))
