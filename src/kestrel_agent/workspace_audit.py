"""Bounded content snapshots: evidence of net workspace changes, never authorization."""
import hashlib
import os
import stat
import time
from pathlib import Path


def snapshot(root: Path, *, max_entries=1000, max_bytes=10_000_000, max_seconds=.1):
    entries, consumed = {}, 0
    deadline = time.monotonic() + max_seconds
    def walk_error(error):
        raise error
    try:
        for directory, dirs, files, directory_fd in os.fwalk(root, follow_symlinks=False, onerror=walk_error):
            for name in sorted(dirs + files):
                if len(entries) >= max_entries or time.monotonic() >= deadline:
                    return {'complete': False, 'entries': entries, 'reason': 'snapshot budget'}
                before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                entry = {'mode': stat.S_IMODE(before.st_mode)}
                if stat.S_ISLNK(before.st_mode):
                    entry.update(type='symlink', target=os.readlink(name, dir_fd=directory_fd))
                elif stat.S_ISDIR(before.st_mode):
                    entry.update(type='directory')
                elif stat.S_ISREG(before.st_mode):
                    consumed += before.st_size
                    if consumed > max_bytes:
                        return {'complete': False, 'entries': entries, 'reason': 'snapshot byte budget'}
                    digest = hashlib.sha256()
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                    with os.fdopen(fd, 'rb') as file:
                        while chunk := file.read(65536):
                            digest.update(chunk)
                            if time.monotonic() >= deadline:
                                return {'complete': False, 'entries': entries, 'reason': 'snapshot time budget'}
                        after = os.fstat(file.fileno())
                    if (before.st_ino, before.st_mtime_ns, before.st_size) != (after.st_ino, after.st_mtime_ns, after.st_size):
                        return {'complete': False, 'entries': entries, 'reason': 'source changed during snapshot'}
                    entry.update(type='file', bytes=before.st_size, sha256=digest.hexdigest())
                else:
                    return {'complete': False, 'entries': entries, 'reason': 'unsupported filesystem entry'}
                entries[str(Path(directory, name).relative_to(root))] = entry
    except OSError:
        return {'complete': False, 'entries': entries, 'reason': 'snapshot unavailable'}
    return {'complete': True, 'entries': entries}


def compare(before, after):
    complete = before['complete'] and after['complete']
    paths = sorted(name for name in before['entries'].keys() | after['entries'].keys()
                   if before['entries'].get(name) != after['entries'].get(name))
    return {'scope': 'workspace', 'complete': complete,
            'unchanged_at_boundaries': not paths if complete else None,
            'changed_paths': paths[:100] if complete else [],
            'changed_paths_omitted': max(0, len(paths) - 100) if complete else None,
            'limitation': 'Net content, path and mode changes between snapshots only; not transient writes or changes outside the workspace.'}
