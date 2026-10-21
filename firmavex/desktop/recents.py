"""A bounded preference index; stored paths never confer project trust."""
from pathlib import Path
import json

from firmavex.backends.engine import _write
from .projects import _safe_root, _read, _object


def _paths(value):
    paths = value.get('paths')
    if type(value.get('schema_version')) is not int or value['schema_version'] != 1 or type(paths) is not list or len(paths) > 10:
        raise ValueError('Invalid recent-project index')
    if any(type(p) is not str or not p or len(p) > 4096 or not p.isprintable() or not Path(p).is_absolute() for p in paths):
        raise ValueError('Invalid recent-project path')
    return list(dict.fromkeys(paths))


def load(data_root):
    root = _safe_root(data_root)
    path = root / 'recent-projects.json'
    if not path.exists() and not path.is_symlink():
        return []
    return _paths(_object(_read(path, maximum=65536)))


def save(data_root, paths):
    value = {'schema_version': 1, 'paths': paths[:10]}
    _paths(value)
    if len(json.dumps(value, sort_keys=True, indent=2).encode('utf-8')) > 65536:
        raise ValueError('Recent-project preferences exceed their byte limit')
    root = _safe_root(data_root)
    root.mkdir(parents=True, exist_ok=True)
    _write(root / 'recent-projects.json', value)


def remember(data_root, project):
    path = str(Path(project).absolute())
    existing = load(data_root)  # Never silently replace an invalid index.
    save(data_root, [path] + [p for p in existing if p != path])
