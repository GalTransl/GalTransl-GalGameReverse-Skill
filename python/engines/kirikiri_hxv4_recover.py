"""Hx recovery workflow: parsed script-name hints plus the archive-only CLI."""
from python.archives.kirikiri_hxv4 import _inflate
from python.archives.kirikiri_hxv4_archive import main
from python.archives.kirikiri_hxv4_static import tjs_strings
from python.common.safety import validate_names
from python.engines.kirikiri_psb import Psb


def script_names(data):
    """Candidates from strictly parsed script constants; hashes remain decisive."""
    if data.startswith(b'mdf\0'):
        if len(data) < 8: raise ValueError('truncated MDF')
        data = _inflate(data[8:], int.from_bytes(data[4:8], 'little'), 32 << 20)
    if data.startswith(b'PSB\0'):
        strings = Psb(data).strings
    elif data.startswith(b'TJS2100\0'):
        strings = tjs_strings(data)
    else:
        return set()
    out = set()
    for s in strings:
        # Filename-like constants only; text/opcodes are never exported as dialogue.
        s = s.replace('\\', '/').rsplit('/', 1)[-1]
        if not s or len(s) > 240 or '.' not in s:
            continue
        variants = [s, s+'.scn'] if s.lower().endswith(('.ks', '.txt')) else [s]
        for name in variants:
            try: validate_names([name])
            except ValueError: continue
            out.add(name)
    return out


if __name__ == '__main__': main(candidate_reader=script_names)
