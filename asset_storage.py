"""Deduplicate newly saved, immutable assets without changing existing paths.

Call only for a fresh upload before its database row is committed. Asset files
must never be edited in place: hard-linked asset IDs share their file contents.
"""
import hashlib
import os
from pathlib import Path
import uuid


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def deduplicate_upload(target, candidates):
    """Return ``sha256`` and whether this upload shares an existing inode.

    Candidate read/link errors are best-effort misses; the fresh upload remains
    usable. Target read errors propagate so callers cannot commit a bad upload.
    Only the newly uploaded target is replaced, atomically, after a link exists.
    """
    target = Path(target)
    digest = file_sha256(target)
    size = target.stat().st_size
    result = {'sha256': digest, 'shared': False}
    for candidate in candidates:
        candidate = Path(candidate)
        temporary = None
        try:
            # Skip self (including alternate paths already pointing at target).
            if os.path.samefile(target, candidate):
                continue
            if not candidate.is_file() or candidate.stat().st_size != size:
                continue
            if file_sha256(candidate) != digest:
                continue
            temporary = target.with_name('.' + target.name + '.link-' + uuid.uuid4().hex)
            os.link(candidate, temporary)
            os.replace(temporary, target)
            return {'sha256': digest, 'shared': True}
        except OSError:
            # Cross-device/unsupported hard links or stale candidates must not
            # turn a successfully uploaded file into a failed upload.
            continue
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
    return result
