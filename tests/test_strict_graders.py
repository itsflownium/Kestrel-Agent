import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('verification',Path(__file__).resolve().parents[1]/'benchmarks/verification.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


def test_recursive_scope_catches_nested_binary_large_and_symlink_changes(tmp_path):
    (tmp_path/'nested').mkdir();(tmp_path/'nested/data.bin').write_bytes(b'\0'*200000)
    before=v.manifest(tmp_path)
    (tmp_path/'nested/data.bin').write_bytes(b'\1'*200000)
    (tmp_path/'link').symlink_to('/does/not/exist')
    after=v.manifest(tmp_path)
    assert {item['path'] for item in v.scope_changes(before,after)}=={'nested/data.bin','link'}
    assert after['link']['type']=='symlink'


def test_new_artifact_parent_directories_are_allowed(tmp_path):
    before=v.manifest(tmp_path)
    (tmp_path/'out').mkdir();(tmp_path/'out/result.json').write_text('{}')
    assert not v.scope_changes(before,v.manifest(tmp_path),created=['out/result.json'])


@pytest.mark.parametrize('answer',['420','Expected output would be TOTAL=42 but the retry command failed.','The command was never executed. TOTAL=42'])
def test_recovery_grade_rejects_substrings_and_counterfactuals(answer):
    assert not v.emitted_result(answer,[{'exit_code':0,'stdout':'TOTAL=42\n'}],'TOTAL','42')


def test_policy_explanation_must_include_relevant_constraints():
    assert not v.policy_answer('{"release":"r21","reason":"yes"}')
    assert v.policy_answer('{"release":"r21","reason":"Newest eligible signed stable release before the cutoff."}')
    with pytest.raises(ValueError):v.policy_answer('```json\n{"release":"r21","reason":"yes"}\n```')
