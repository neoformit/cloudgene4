"""
Validates docs/examples/cloudgene.yaml — the complete example in
docs/WORKFLOW_YAML_REFERENCE.md — against the real parser, so the reference documentation
cannot silently drift from what workflows.definition actually accepts.
"""
from pathlib import Path

from django.test import SimpleTestCase

from workflows.definition import (CHOICE_TYPES, DISPLAY_TYPES, FILE_TYPES, INPUT_TYPES,
                                  OUTPUT_TYPES, load_definition)

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / 'docs' / 'examples' / 'cloudgene.yaml'


class YamlReferenceExampleTest(SimpleTestCase):
    """docs/examples/cloudgene.yaml must load cleanly with no errors or warnings."""

    def setUp(self):
        self.assertTrue(EXAMPLE_PATH.is_file(), f'{EXAMPLE_PATH} is missing')
        self.definition = load_definition(EXAMPLE_PATH)

    def test_top_level_fields(self):
        d = self.definition
        self.assertEqual(d.id, 'reference-example')
        self.assertEqual(d.name, 'Reference Example')
        self.assertEqual(d.version, '1.2.3')
        self.assertTrue(d.description)
        self.assertEqual(d.website, 'https://example.org/reference-example')
        self.assertEqual(d.author, 'Cloudgene Docs')
        self.assertEqual(d.category, 'examples')

    def test_no_errors_or_warnings(self):
        # load_definition() itself raises DefinitionError on any error; reaching here means
        # there were none. Warnings (e.g. an unsupported step, a dropped default) would still
        # be silently accepted, so assert there are none for this reference document either.
        self.assertEqual(self.definition.warnings, [])

    def test_steps(self):
        steps = self.definition.steps
        self.assertEqual([s.type for s in steps], ['nextflow', 'nextflow', 'command', 'command'])
        for step in steps:
            self.assertTrue(step.supported)
        self.assertEqual([s.script for s in steps[:2]], ['main.nf', 'main.nf'])
        self.assertFalse(steps[2].bash)
        self.assertTrue(steps[3].bash)
        self.assertTrue(steps[2].stdout and steps[2].stderr)

    def test_every_input_type_is_demonstrated(self):
        used_types = {i.type for i in self.definition.inputs}
        self.assertEqual(used_types, set(INPUT_TYPES),
                         'the example should cover every documented input type exactly once')

    def test_input_ids_unique_and_valid(self):
        ids = [i.id for i in self.definition.inputs] + [o.id for o in self.definition.outputs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_display_inputs_never_serialized(self):
        for i in self.definition.inputs:
            if i.type in DISPLAY_TYPES:
                self.assertFalse(i.serialize)
                self.assertFalse(i.required)

    def test_outputs(self):
        outputs = {o.id: o for o in self.definition.outputs}
        self.assertEqual(set(outputs), {'results', 'report', 'intermediate'})
        self.assertTrue(outputs['results'].download)
        self.assertFalse(outputs['intermediate'].download)
        for o in self.definition.outputs:
            self.assertIn(o.type, OUTPUT_TYPES)

    def test_choice_and_file_inputs_present(self):
        by_id = {i.id: i for i in self.definition.inputs}
        self.assertEqual(by_id['reference_genome'].type, 'list')
        self.assertIn(by_id['reference_genome'].type, CHOICE_TYPES)
        self.assertEqual(by_id['reference_genome'].value, 'GRCh38')
        self.assertIn(by_id['input_vcf'].type, FILE_TYPES)
        self.assertEqual(by_id['input_vcf'].accept_extensions, ['.vcf', '.vcf.gz'])
        self.assertTrue(by_id['comments'].write_file)
        self.assertFalse(by_id['hidden_default'].visible)
        self.assertFalse(by_id['not_sent_to_pipeline'].serialize)
