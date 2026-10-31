"""Delete-only line-break policy shared by engine text writers.

Several formats store display line breaks as literal characters or control
tags inside a variable-length string. A shorter translation may use fewer
display lines, but it must not add a break or move one across another control
token: font spans, ruby readings and runtime tags are positioned relative to
the original control sequence. Engines that index fixed physical line slots
still pad empty slots in their own writer and do not call this module.
"""


def _split(tokens, is_break):
    """Return non-break tokens plus the break tokens of each gap between them."""
    rest, gaps = [], [[]]
    for token in tokens:
        if is_break(token):
            gaps[-1].append(token)
        else:
            rest.append(token)
            gaps.append([])
    return rest, gaps


def drops_only_line_breaks(before, after, is_break):
    """True when ``after`` keeps the control tokens and only removes breaks.

    ``before`` and ``after`` are ordered control-token sequences (not plain
    text). Non-break tokens must stay identical and in order. Each gap in
    ``after`` must be a prefix of the same original gap, so a translation may
    delete breaks between two controls but cannot add, retype or move one
    across another control token.
    """
    old_rest, old_gaps = _split(before, is_break)
    new_rest, new_gaps = _split(after, is_break)
    if old_rest != new_rest:
        return False
    return all(old[:len(new)] == new for old, new in zip(old_gaps, new_gaps))
