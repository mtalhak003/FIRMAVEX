"""Presentation-only error guidance; no runtime result or admission is changed."""
import copy

import pytest

from firmavex.desktop.diagnostics import operation_error_text


@pytest.mark.parametrize('category,phrase', [
    ('missing_dependency', 'runtime setup / repair'), ('dependency_probe_failed', 'availability is not'),
    ('unsupported_platform', 'without disabling admission'), ('unsupported_runtime', 'compatible runtime'),
    ('runtime_pack_invalid', 'trusted runtime generation'), ('invalid_firmware', 'Raw BIN'),
    ('unsupported_firmware', 'MPS2 ELF contract'), ('invalid_configuration', 'validate again'),
    ('configuration_error', 'validate again'), ('invalid_input', 'two uint32'),
    ('cancelled', 'not a passing test'), ('worker_interrupted', 'remains unknown'),
    ('worker_timeout', 'infrastructure failure'), ('infrastructure_failure', 'not a safe result'),
    ('invalid_output', 'trigger alone'), ('firmware_changed', 'separate project or revision'),
    ('toolchain_changed', 'separate project'), ('output_exists', 'must not be overwritten'),
    ('incomplete_run', 'terminal result'), ('no_saved_trigger', 'exact triggering vector'),
])
def test_guidance_preserves_category_and_offers_specific_next_action(category, phrase):
    result = operation_error_text({'category': category, 'message': 'Recorded failure'})
    assert result.startswith(category + ': Recorded failure\nNext: ')
    assert phrase in result


def test_summary_does_not_copy_or_mutate_administrative_details():
    error = {'category': 'missing_dependency', 'message': 'Tool unavailable',
             'details': {'credential': 'private-value', 'stderr': 'unbounded raw output', 'attempts': 42}}
    before = copy.deepcopy(error)
    result = operation_error_text(error)
    assert error == before
    assert 'private-value' not in result and 'unbounded raw output' not in result and '42' not in result


@pytest.mark.parametrize('value', [None, [], True, 'unexpected', {'category': [], 'message': False}])
def test_malformed_errors_have_actionable_fallback(value):
    result = operation_error_text(value)
    assert result.startswith('operation_failed: The operation could not be completed.')
    assert 'No successful execution is assumed.' in result


def test_display_work_and_output_are_bounded_and_controls_visible():
    result = operation_error_text({'category': 'x'*1000000, 'message': '\x1b\n\t' + 'y'*1000000})
    assert len(result) < 1800
    assert '\x1b' not in result and '\t' not in result and result.count('\n') == 1
    assert '\ufffd' in result and '…' in result


@pytest.mark.parametrize('operation', ['export', 'backend_export', 'backend_verification_report', 'export_verification_report'])
def test_failed_export_never_claims_completion(operation):
    result = operation_error_text({'category': 'output_exists', 'message': 'Destination exists'}, operation)
    assert 'No completed export is confirmed.' in result and 'new writable destination' in result


def test_unknown_categories_do_not_suggest_unsafe_retry_or_fake_success():
    result = operation_error_text({'category': 'future_error', 'message': 'Unknown outcome'})
    assert 'future_error: Unknown outcome' in result
    assert 'No successful execution is assumed.' in result


@pytest.mark.parametrize('operation', [[], {}, True])
def test_malformed_operation_context_does_not_break_error_display(operation):
    assert operation_error_text({'category': 'cancelled'}, operation).startswith('cancelled:')
