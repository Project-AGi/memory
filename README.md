# Memory

Memory is the shared memory component for AGi agents, including **AIVA** (hosted
by AIVA) and **Aiko**. It owns reusable memory APIs and storage; AIVA remains
the runtime that connects AIVA's chat, ROS topics, and user interface.

## Current scope

Memory currently provides two distinct pieces:

- A general memory API with journal and SQLite backends for structured entries.
- `memory.conversation.ConversationStore`, a SQLite store for paired user and
  assistant turns. AIVA uses this store for AIVA's chat history and adds its
  own Canvas-specific study and context behavior in `AivaMemory`.

Conversation history is persistent. `recent()` returns only the configured
number of latest exchanges for active context; it does not delete older turns
or perform semantic retrieval. The conversation store reuses the
`conversations` and `conversation_turns` tables used by AIVA, so existing
databases can be opened in place. Memory owns the shared storage implementation;
the host application chooses the database path and its application-specific
policies.

## Design

- **One contract**: `memory.api` defines the `Entry` shape and the
  `MemoryBackend` interface (append / search / recent / close).
- **Pluggable backends**: journal (append-only JSONL, default), sqlite;
  vector stores arrive later behind the same interface.
- **Conformance suite**: `memory.conformance.run_all(name, factory)` — every
  backend, bundled or future (ROS2-wrapped server, vector DB), must pass it.
- **Single writer**: one process owns a store; concurrency is the server
  layer's job. The journal file is safe for concurrent *readers*.
- **Explainable ranking**: recency half-life + importance + word overlap
  (`memory.scoring`) — the debuggable baseline before embeddings.

## Usage

```python
import os
from memory import open_memory

agi_home = os.environ.get('AGI_HOME', '~/.agi')
mem = open_memory(f'{agi_home}/profile/aiva.jsonl')   # or aiva.db
mem.append({'agent': 'aiva', 'kind': 'dialogue',
            'text': 'OppaAI asked me to draw a mug',
            'tags': ['drawing'], 'importance': 0.7})
mem.search('mug drawing')
mem.recent(agent='aiva', limit=20)
```

## Python package

The reusable Python library lives in `src/memory/` and installs into a Python
environment with pip. It is not a ROS package or node. AIVA's `aiva_chat` imports
`memory.conversation` directly and uses a local SQLite database. A separate ROS
memory service would only be useful if multiple processes needed to share one
store over ROS.

## Install

```bash
cd AIVA
.venv/bin/python -m pip install -e ./mind/memory
```

When hosted by AIVA, its virtual environment and `AGI_HOME` defaults are defined
in [AIVA's `spec.yaml`](../../spec.yaml). The runtime can override `AGI_HOME`
through `AIVA/.env`.

No third-party dependencies; stdlib only.


## Conversation history

`memory.conversation.ConversationStore` saves each user/assistant exchange
together and returns the latest exchanges for a given conversation, oldest
first. The recall window does not delete older exchanges.

```python
import os
from memory.conversation import ConversationStore

agi_home = os.environ.get("AGI_HOME", "~/.agi")
store = ConversationStore(f"{agi_home}/profile/aiva_memory.sqlite3", max_turns=8)
store.add_exchange("Hello AIVA", "Hi!")
recent = store.recent()
```

Install Memory into the Python environment that runs the application. AIVA's
`requirements.txt` installs the package from this repository. For local
development, install the checkout with `pip install -e .` from the Memory repository root.

The API deliberately returns simple role/content dictionaries suitable for a
chat completion request. It does not call a language model, choose tools, or
decide which memories are relevant. Those behaviors belong to the application
or future Memory components.

## Conversation action memory

`memory.conversation.ConversationStore` also persists agent actions in `conversation_events` alongside its existing conversation tables. `record_event(text, kind='event', metadata=None)` writes a timestamped event immediately. `recall_events(query='', kind='event', limit=8)` returns relevant/recent events scoped to the active conversation. This is bounded lexical retrieval and recency, not semantic embedding recall. Events survive restarts without appearing as invented user messages.

Interactive uses `kind='lighting'` to retain effect choices, brief reasons, personal signal meanings and tool outcomes, including when a following LLM reply fails. The ordinary chat window and its turn limit remain independent of these stored records.
