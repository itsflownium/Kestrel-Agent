from benchmarks.browser_agent import grade


def completed_record():
    return {'target':'Record-unique','status':'completed','submitted':[{'name':'Record-unique'}],
            'unexpected_files':[], 'answer':'Saved Record-unique',
            'observations':[{'tool':'mcp','status':'completed','result':{'structuredContent':{'text':'Saved record: Record-unique'}}}]}


def test_browser_grader_requires_actual_effect_visible_observation_and_scope():
    assert grade(completed_record()) == (True, True)
    for changes in [
        {'submitted':[]}, {'submitted':[{'name':'wrong'}]},
        {'submitted':[{'name':'Record-unique'},{'name':'Record-unique'}]},
        {'observations':[]}, {'unexpected_files':['unrequested.txt']},
        {'status':'error'}, {'answer':'Done'}, {'answer':None},
    ]:
        record = completed_record()
        record.update(changes)
        assert not grade(record)[0]
    record = completed_record()
    record['observations'][0]['tool'] = 'generate'
    assert not grade(record)[0]  # A model's claim is not a browser observation.
    record = completed_record()
    record['observations'][0]['status'] = 'error'
    assert not grade(record)[0]


def test_browser_grader_accepts_native_json_tool_results_but_not_plain_claims():
    import json
    record = completed_record()
    record['observations'][0]['result'] = {'structuredContent':None, 'content':[{'type':'text','text':json.dumps({'text':'Saved record: Record-unique'})}]}
    assert grade(record) == (True, True)
    record['observations'][0]['result']['content'][0]['text'] = 'Saved record: Record-unique'
    assert grade(record) == (False, False)
    record['observations'][0]['result'] = None
    assert grade(record) == (False, False)


def test_native_baseline_rejects_other_connector_calls():
    record = completed_record()
    record['mode'] = 'direct-codex'
    record['observations'][0]['server'] = 'kestrel_browser_fixture'
    assert grade(record)[0]
    record['observations'].append({'tool':'mcp','server':'unrelated','status':'failed'})
    assert not grade(record)[0]
