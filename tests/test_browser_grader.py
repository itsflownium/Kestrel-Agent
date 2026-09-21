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
        {'status':'error'}, {'answer':'Done'},
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
