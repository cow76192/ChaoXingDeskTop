"""Shared public-distribution boundary for portable and installed releases."""
import os
from pathlib import Path
import stat


def validate_app_tree(root):
    root = Path(root)
    forbidden = {'settings.ini', 'config.ini', 'cookies.txt', 'cookies.dat', 'accounts.json', 'credentials.json', '.env'}
    files = []
    def check(path):
        info = path.lstat()
        if path.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f'Unexpected link/reparse point in application: {path.name}')
    check(root)
    for directory, folders, names in os.walk(root, followlinks=False):
        for name in folders:
            check(Path(directory) / name)
        for name in names:
            path = Path(directory) / name
            check(path)
            relative = path.relative_to(root).as_posix()
            lower = name.lower()
            if (lower in forbidden or lower.startswith('.env.')
                    or (lower.startswith('cookies') and path.suffix.lower() in {'.txt', '.dat'})
                    or path.suffix.lower() in {'.ini', '.log', '.key', '.p12', '.pfx', '.tmp', '.bak'}
                    or (path.suffix.lower() == '.pem' and relative != '_internal/certifi/cacert.pem')):
                raise ValueError(f'Private or temporary file in application: {relative}')
            files.append(path)
    return sorted(files)
