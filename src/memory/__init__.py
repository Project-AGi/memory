"""memory - the AGi memory framework.

One contract (`memory.api`), pluggable backends, one conformance suite
(`memory.conformance`) that every backend must pass. AIVA (PC, AIVA) and
Aiko (Jetson) both speak this; ROS2 and non-ROS processes alike.

    from memory import open_memory
    mem = open_memory('~/AGi/memory/aiva.jsonl')
    mem.append({'agent': 'aiva', 'kind': 'dialogue',
                'text': 'OppaAI asked me to draw a mug', 'importance': 0.7})
    mem.search('mug')
"""
from .api import (ENTRY_SCHEMA, KINDS, MemoryBackend, normalize, open_memory)
from . import scoring

__all__ = ['ENTRY_SCHEMA', 'KINDS', 'MemoryBackend', 'normalize',
           'open_memory', 'scoring']
__version__ = '0.1.0'
