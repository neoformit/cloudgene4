"""
Progress parsing for Nextflow runs (pure, no DB): stdout annotations, stdout task lines,
the trace file and per-process task counts. Used incrementally by the worker every tick.

Annotations (Cloudgene 3 / GitHub-Actions style, see cloudgene3 docs/developers/reporting.md)::

    ::message::text   ::notice::text   ::warning::text   ::error::text   ::debug::text
    ::group type=error::        (following plain lines are collected)
    ::endgroup::                (emits one message of the group's type)
"""
from __future__ import annotations

import os
import re
from collections import Counter, OrderedDict

LEVELS = {
    'message': 'info', 'notice': 'info', 'info': 'info', 'success': 'success',
    'warning': 'warning', 'error': 'error', 'debug': 'debug',
}
MAX_MESSAGE_LENGTH = 10000

# "[PROCESS ab/123456] name (1)" (Nextflow >= 25) and
# "[ab/123456] Submitted process > name (1)" / "Cached process >" (older versions).
_TASK_NEW = re.compile(r'^\[PROCESS ([0-9a-f]{2}/[0-9a-f]{6})\] (.+?)\s*$')
_TASK_OLD = re.compile(r'^\[([0-9a-f]{2}/[0-9a-f]{6})\] (Submitted|Cached|Re-submitted) process > (.+?)\s*$')
_TAG_SUFFIX = re.compile(r'\s+\(.*\)$')

FINAL_OK = ('COMPLETED', 'CACHED')
FINAL_FAIL = ('FAILED', 'ABORTED', 'KILLED')


def process_name(task_name: str) -> str:
    """``"WF:sayHello (2)"`` -> ``"WF:sayHello"``."""
    return _TAG_SUFFIX.sub('', task_name.strip())


class LineBuffer:
    """Splits a stream fed in chunks into complete lines (a trailing partial line is kept)."""

    def __init__(self):
        self._partial = ''

    def feed(self, text: str) -> list[str]:
        data = self._partial + text
        lines = data.split('\n')
        self._partial = lines.pop()
        return [line.rstrip('\r') for line in lines]

    def flush(self) -> list[str]:
        rest, self._partial = self._partial, ''
        return [rest.rstrip('\r')] if rest else []


def _parse_command(line: str):
    """``::name k=v,k2=v2::value`` -> (name, params, value) or None."""
    body = line[2:]
    head, sep, value = body.partition('::')
    if not sep:
        return None
    name, _, param_text = head.strip().partition(' ')
    name = name.strip().lower()
    if not name or not re.match(r'^[a-z][a-z-]*$', name):
        return None
    params = {}
    for pair in param_text.split(','):
        key, eq, val = pair.partition('=')
        if eq and key.strip():
            params[key.strip()] = val.strip()
    return name, params, value.strip()


class AnnotationParser:
    """Incremental annotation parser. ``feed_line`` returns a list of ``(level, text)``."""

    def __init__(self):
        self._group = None   # (level, [lines])

    def feed_line(self, line: str) -> list[tuple[str, str]]:
        stripped = line.strip()
        if stripped.startswith('::'):
            cmd = _parse_command(stripped)
            if cmd is not None:
                name, params, value = cmd
                if name == 'group':
                    out = self.close()
                    level = LEVELS.get(params.get('type', 'message').lower(), 'info')
                    self._group = (level, [value] if value else [])
                    return out
                if name == 'endgroup':
                    return self.close()
                level = LEVELS.get(name)
                if level is None or level == 'debug':
                    return []   # counters/values/log/debug: not user-visible messages
                if not value:
                    return []
                return [(level, value[:MAX_MESSAGE_LENGTH])]
        if self._group is not None:
            self._group[1].append(line)
        return []

    def feed_lines(self, lines) -> list[tuple[str, str]]:
        out = []
        for line in lines:
            out.extend(self.feed_line(line))
        return out

    def close(self) -> list[tuple[str, str]]:
        """Emit an open group (called on ``::endgroup::`` or at end of stream)."""
        if self._group is None:
            return []
        level, lines = self._group
        self._group = None
        text = '\n'.join(lines).strip()
        return [(level, text[:MAX_MESSAGE_LENGTH])] if text else []


def parse_annotations(text: str) -> list[tuple[str, str]]:
    parser = AnnotationParser()
    out = parser.feed_lines(text.splitlines())
    return out + parser.close()


def parse_task_line(line: str):
    """Nextflow stdout task line -> ``(hash, process_name, cached)`` or None."""
    m = _TASK_NEW.match(line)
    if m:
        return m.group(1), process_name(m.group(2)), False
    m = _TASK_OLD.match(line)
    if m:
        return m.group(1), process_name(m.group(3)), m.group(2) == 'Cached'
    return None


class TraceReader:
    """Incrementally reads a Nextflow trace file (tab separated, header line first)."""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.header = None
        self._buf = LineBuffer()

    def read(self) -> list[dict]:
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        if size < self.offset:           # file was rewritten
            self.offset, self.header, self._buf = 0, None, LineBuffer()
        if size == self.offset:
            return []
        with open(self.path, 'rb') as fh:
            fh.seek(self.offset)
            chunk = fh.read(size - self.offset)
        self.offset = size
        return self.parse_lines(self._buf.feed(chunk.decode('utf-8', 'replace')))

    def parse_lines(self, lines) -> list[dict]:
        rows = []
        for line in lines:
            if not line.strip():
                continue
            cols = line.split('\t')
            if self.header is None:
                self.header = [c.strip() for c in cols]
                continue
            rows.append(dict(zip(self.header, cols)))
        return rows


class ProcessTracker:
    """Per-process task counts from stdout task lines and trace rows."""

    def __init__(self, labels: dict | None = None):
        self.labels = labels or {}          # process name -> display label (from YAML)
        self.tasks = OrderedDict()          # hash -> [process, state]  (state: submitted|completed|failed)
        self.order = []                     # process names in first-seen order
        self.changed = False

    def _see(self, process):
        if process not in self.order:
            self.order.append(process)

    def submitted(self, task_hash, process, cached=False):
        self._see(process)
        if task_hash not in self.tasks:
            self.tasks[task_hash] = [process, 'completed' if cached else 'submitted']
            self.changed = True

    def trace_row(self, row: dict):
        name = row.get('process') or process_name(row.get('name', ''))
        if not name:
            return
        status = (row.get('status') or '').strip().upper()
        key = row.get('hash') or f"task-{row.get('task_id', len(self.tasks))}"
        self._see(name)
        if status in FINAL_OK:
            state = 'completed'
        elif status in FINAL_FAIL:
            state = 'failed'
        else:
            state = 'submitted'
        current = self.tasks.get(key)
        if current is None or current[1] != state:
            self.tasks[key] = [name, state]
            self.changed = True

    def kill_unfinished(self):
        for task in self.tasks.values():
            if task[1] == 'submitted':
                task[1] = 'failed'
                self.changed = True

    def counts(self) -> list[dict]:
        out = []
        for name in self.order:
            c = Counter(state for proc, state in self.tasks.values() if proc == name)
            completed, failed, running = c['completed'], c['failed'], c['submitted']
            out.append({
                'name': name, 'label': self.labels.get(name) or self.labels.get(name.split(':')[-1]) or name,
                'submitted': completed + failed + running, 'running': running,
                'completed': completed, 'failed': failed, 'total': completed + failed + running,
            })
        return out


class MessageMerger:
    """Merges messages from several sources (nextflow stdout, per-task ``.command.out``) without
    duplicates: a (level, text) seen n times in one source and m times in another is emitted
    max(n, m) times. This matters because a ``debug true`` process prints to both."""

    def __init__(self):
        self.emitted = Counter()
        self.by_source = {}

    def add(self, source: str, messages) -> list[tuple[str, str]]:
        seen = self.by_source.setdefault(source, Counter())
        out = []
        for msg in messages:
            seen[msg] += 1
            if seen[msg] > self.emitted[msg]:
                self.emitted[msg] += 1
                out.append(msg)
        return out


def read_task_annotations(workdir: str) -> list[tuple[str, str]]:
    """Annotations of a finished task (``cloudgene.out`` if present, else ``.command.out``)."""
    if not workdir:
        return []
    for name in ('cloudgene.out', '.command.out'):
        path = os.path.join(workdir, name)
        try:
            with open(path, 'rb') as fh:
                data = fh.read(2 * 1024 * 1024)
        except OSError:
            continue
        return parse_annotations(data.decode('utf-8', 'replace'))
    return []
