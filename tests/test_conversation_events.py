from memory.conversation import ConversationStore


def test_actions_survive_restart_and_recall_outside_recent_window(tmp_path):
    path = tmp_path / 'conversation.db'
    store = ConversationStore(path, max_turns=1)
    store.record_event('Changed to blue because the conversation was calm', kind='lighting',
                       metadata={'reason': 'calm', 'meaning': 'blue means quiet company'})
    for n in range(5):
        store.add_exchange(f'Hello {n}', 'Hello')
    restarted = ConversationStore(path, max_turns=1)
    assert len(restarted.recent()) == 2
    hits = restarted.recall_events('blue', kind='lighting')
    assert hits[0]['metadata']['meaning'] == 'blue means quiet company'
    assert 'because' in hits[0]['text']
    restarted.conversation_id = 'different'
    restarted.add_exchange('Hi', 'Hi')
    assert restarted.recall_events('blue', kind='lighting') == []


def test_recall_ranks_matching_reason_before_newest_event(tmp_path):
    store = ConversationStore(tmp_path / 'conversation.db')
    store.record_event('pink means sakura', kind='lighting')
    store.record_event('I chose red', kind='lighting')
    assert 'pink' in store.recall_events('pink', kind='lighting')[0]['text']
    assert len(store.recall_events("' OR 1=1 --", kind='lighting', limit=1)) == 1


def test_action_can_be_recorded_before_first_exchange_in_new_conversation(tmp_path):
    path = tmp_path / 'conversation.db'
    store = ConversationStore(path)
    store.conversation_id = 'new-conversation'
    store.record_event('Selected a quiet colour', kind='lighting', metadata={'reason': 'quiet'})
    store.add_exchange('Hello', 'Welcome')
    restarted = ConversationStore(path)
    restarted.conversation_id = 'new-conversation'
    assert restarted.recall_events(kind='lighting')[0]['metadata']['reason'] == 'quiet'
    assert restarted.recent()[-1]['content'] == 'Welcome'


def test_empty_recall_query_returns_latest_events(tmp_path):
    store = ConversationStore(tmp_path / 'conversation.db')
    store.record_event('First')
    store.record_event('Second')
    assert [item['text'] for item in store.recall_events()] == ['Second', 'First']
