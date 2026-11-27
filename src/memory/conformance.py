"""The conformance suite: every memory backend must pass these exact tests.

Future backends (vector stores, a ROS2-wrapped server) implement the same
factory and get the whole suite for free:

    from memory.conformance import run_all
    run_all("my-backend", lambda: MyBackend(...))
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def run_all(name, factory):
    """Assert the full contract against a freshly created backend.

    factory() -> open backend; factory(reopen=path) -> reopened at same data.
    Simple factories should ignore the argument and build a temp store.
    """
    from . import api
    assert callable(factory)
    backend = factory()
    try:
        # ---- normalize + append -------------------------------------
        stored = backend.append({'agent': 'aiva', 'kind': 'observation',
                                 'text': 'Drew a mug on the canvas today',
                                 'tags': ['drawing', 'mug'], 'importance': 0.8})
        assert stored['ts'] > 0 and stored['kind'] == 'observation'
        assert stored['tags'] == ['drawing', 'mug']
        assert stored['importance'] == 0.8

        # defaults filled
        second = backend.append({'text': 'Aiko watched the snow fall'})
        assert second['agent'] and second['kind'] in api.KINDS

        # garbage rejected
        for bad in ('not a dict', {'kind': 'event'}, {'text': ''}, {'text': 'x', 'kind': 'weird'}):
            try:
                backend.append(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f'{name}: accepted invalid entry {bad!r}')

        # ---- search ---------------------------------------------------
        backend.append({'agent': 'aiko', 'kind': 'dialogue',
                        'text': 'OppaAI asked about the mug drawing',
                        'importance': 0.6})
        hits = backend.search('mug drawing')
        assert hits, f'{name}: search found nothing'
        assert 'mug' in hits[0]['text'].lower(), f'{name}: wrong top hit'

        # ---- recent ---------------------------------------------------
        recent = backend.recent(limit=2)
        assert len(recent) <= 2 and recent[0]['ts'] >= recent[1]['ts']
        by_agent = backend.recent(agent='aiko')
        assert all(e['agent'] == 'aiko' for e in by_agent)

        # ---- close + reopen persistence --------------------------------
        ts_before = backend.recent(limit=1)[0]['ts']
        path = getattr(backend, 'path', None)
        backend.close()
        reopened = (type(backend)(path) if path is not None else factory())
        try:
            again = reopened.search('snow')
            assert any('snow' in e['text'].lower() for e in again), \
                f'{name}: data lost after reopen'
            assert reopened.recent(limit=1)[0]['ts'] == ts_before
        finally:
            reopened.close()
    finally:
        try:
            backend.close()
        except Exception:
            pass
    return True


def bundled_factories():
    """Factories for the bundled backends, used by the test suite."""
    from .journal import JournalBackend
    from .sqlite_store import SqliteBackend

    def journal_factory(reopen=None):
        return JournalBackend(Path(tempfile.mkdtemp()) / 'mem.jsonl')

    def sqlite_factory(reopen=None):
        return SqliteBackend(Path(tempfile.mkdtemp()) / 'mem.db')

    return {'journal': journal_factory, 'sqlite': sqlite_factory}
