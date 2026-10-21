import json
from pathlib import Path

import pytest

from firmavex.desktop.recents import load, save, remember
from firmavex.product.errors import ProductError


def test_recent_paths_are_bounded_deduplicated_and_explicit(tmp_path):
    root = tmp_path / 'preferences'
    assert load(root) == []
    for i in range(12):
        remember(root, tmp_path / str(i))
    assert len(load(root)) == 10
    remember(root, tmp_path / '10')
    paths = load(root)
    assert paths[0] == str(tmp_path / '10') and len(set(paths)) == 10
    # Paths need not exist. Loading preferences must not create/open projects.
    assert not (tmp_path / '10').exists()
    save(root, paths[1:])
    assert str(tmp_path / '10') not in load(root)


@pytest.mark.parametrize('value', [{}, {'schema_version': 1, 'paths': ['relative']},
    {'schema_version': 1, 'paths': [None]}, {'schema_version': 1, 'paths': ['/x'] * 11}])
def test_malformed_preferences_are_not_overwritten(tmp_path, value):
    path = tmp_path / 'recent-projects.json'
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    with pytest.raises(ValueError):
        remember(tmp_path, tmp_path / 'project')
    assert path.read_bytes() == before


def test_symlink_index_is_rejected_without_touching_target(tmp_path):
    target = tmp_path / 'target'; target.write_text('private data')
    try:
        (tmp_path / 'recent-projects.json').symlink_to(target)
    except OSError:
        pytest.skip('Host does not permit symlinks')
    with pytest.raises(ProductError):
        load(tmp_path)
    assert target.read_text() == 'private data'
