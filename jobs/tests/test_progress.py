import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from jobs.progress import (AnnotationParser, LineBuffer, MessageMerger, ProcessTracker, TraceReader,
                           parse_annotations, parse_task_line, process_name, read_task_annotations)


class AnnotationParserTest(SimpleTestCase):
    def test_levels(self):
        text = ('::message::Hello world\n::notice::note\n::warning::careful\n::error::bad\n'
                '::debug::hidden\n::set-counter name=x::5\nplain line\n::message::\n')
        self.assertEqual(parse_annotations(text), [
            ('info', 'Hello world'), ('info', 'note'), ('warning', 'careful'), ('error', 'bad')])

    def test_value_may_contain_colons(self):
        self.assertEqual(parse_annotations('::message::a::b: c\n'), [('info', 'a::b: c')])

    def test_group(self):
        text = '::group type=error::\nline 1\n- line 2\n::endgroup::\n::group::Title\nx\n::endgroup::\n'
        self.assertEqual(parse_annotations(text), [('error', 'line 1\n- line 2'), ('info', 'Title\nx')])

    def test_unterminated_group_flushed_on_close(self):
        p = AnnotationParser()
        self.assertEqual(p.feed_lines(['::group type=warning::', 'a']), [])
        self.assertEqual(p.close(), [('warning', 'a')])

    def test_unicode_and_invalid(self):
        self.assertEqual(parse_annotations('::message::Grüße 🚀\n::not valid\n:: x::y\n'),
                         [('info', 'Grüße 🚀')])


class LineBufferTest(SimpleTestCase):
    def test_partial_lines(self):
        b = LineBuffer()
        self.assertEqual(b.feed('ab'), [])
        self.assertEqual(b.feed('c\nde'), ['abc'])
        self.assertEqual(b.feed('f\r\n'), ['def'])
        self.assertEqual(b.feed('tail'), [])
        self.assertEqual(b.flush(), ['tail'])


class TaskLineTest(SimpleTestCase):
    def test_formats(self):
        self.assertEqual(parse_task_line('[PROCESS f6/a71873] sayHello (2)'), ('f6/a71873', 'sayHello', False))
        self.assertEqual(parse_task_line('[ab/123456] Submitted process > WF:ALIGN (sample 1)'),
                         ('ab/123456', 'WF:ALIGN', False))
        self.assertEqual(parse_task_line('[ab/123456] Cached process > X'), ('ab/123456', 'X', True))
        self.assertIsNone(parse_task_line('::message::x'))
        self.assertEqual(process_name('A:B (1)'), 'A:B')


class TraceAndTrackerTest(SimpleTestCase):
    def test_incremental_trace_and_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace.txt'
            reader = TraceReader(path)
            self.assertEqual(reader.read(), [])
            path.write_text('task_id\thash\tprocess\tname\tstatus\n1\taa/000001\tA\tA (1)\tCOMPLETED\n2\taa/00')
            rows = reader.read()
            self.assertEqual([r['hash'] for r in rows], ['aa/000001'])
            with open(path, 'a') as fh:
                fh.write('0002\tB\tB (1)\tFAILED\n')
            rows2 = reader.read()
            self.assertEqual(rows2[0]['status'], 'FAILED')
            t = ProcessTracker({'A': 'Process A'})
            t.submitted('aa/000001', 'A')
            t.submitted('aa/000003', 'A')
            t.submitted('aa/000002', 'B')
            for r in rows + rows2:
                t.trace_row(r)
            counts = {c['name']: c for c in t.counts()}
            self.assertEqual(counts['A']['label'], 'Process A')
            self.assertEqual((counts['A']['completed'], counts['A']['running'], counts['A']['total']), (1, 1, 2))
            self.assertEqual((counts['B']['failed'], counts['B']['running']), (1, 0))
            t.kill_unfinished()
            self.assertEqual({c['name']: c['failed'] for c in t.counts()}['A'], 1)

    def test_trace_without_process_column(self):
        t = ProcessTracker()
        t.trace_row({'name': 'WF:X (3)', 'status': 'CACHED', 'hash': 'x'})
        self.assertEqual(t.counts()[0]['name'], 'WF:X')
        self.assertEqual(t.counts()[0]['completed'], 1)


class MergerTest(SimpleTestCase):
    def test_dedup_between_sources(self):
        m = MessageMerger()
        msg = ('info', 'hi')
        self.assertEqual(m.add('tasks', [msg]), [msg])
        self.assertEqual(m.add('stdout', [msg]), [])        # same message echoed by debug process
        self.assertEqual(m.add('stdout', [msg]), [msg])     # second real occurrence
        self.assertEqual(m.add('tasks', [msg, ('warning', 'w')]), [('warning', 'w')])

    def test_read_task_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(read_task_annotations(tmp), [])
            (Path(tmp) / '.command.out').write_text('::message::from task\n')
            self.assertEqual(read_task_annotations(tmp), [('info', 'from task')])
            (Path(tmp) / 'cloudgene.out').write_text('::warning::preferred\n')
            self.assertEqual(read_task_annotations(tmp), [('warning', 'preferred')])
