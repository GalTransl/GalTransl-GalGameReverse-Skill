"""Compact AES (128/192/256) with CBC and PKCS#7; standard library only.

Written for archives that encrypt members with AES-CBC but have no shipped
codec in this skill. The S-box is generated from the GF(2^8) inverse and the
affine transform, so the table cannot drift from the algorithm; block and CBC
behaviour are checked against FIPS-197 and SP 800-38A vectors in the tests.

Scope: single-block primitives plus CBC with optional padding. No GCM, CTR,
streaming, or key derivation. Pure Python speed is roughly hundreds of KiB/s,
so callers must keep their own file-size budgets.
"""

BLOCK_SIZE = 16

_SBOX = None
_INV_SBOX = None


def _xtime(value):
    return ((value << 1) ^ 0x1B) & 0xFF if value & 0x80 else value << 1


def _mul(left, right):
    result = 0
    while right:
        if right & 1:
            result ^= left
        left = _xtime(left)
        right >>= 1
    return result


def _build_sbox():
    sbox = [0] * 256
    p = q = 1
    while True:
        p = p ^ _xtime(p)
        p &= 0xFF
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        value = q
        for shift in (1, 2, 3, 4):
            value ^= ((q << shift) | (q >> (8 - shift))) & 0xFF
        sbox[p] = value ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


def _tables():
    global _SBOX, _INV_SBOX
    if _SBOX is None:
        sbox = _build_sbox()
        inverse = [0] * 256
        for index, value in enumerate(sbox):
            inverse[value] = index
        _SBOX, _INV_SBOX = sbox, inverse
    return _SBOX, _INV_SBOX


def _expand_key(key):
    sbox, _ = _tables()
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24 or 32 bytes")
    words = len(key) // 4
    rounds = words + 6
    schedule = [list(key[index * 4:index * 4 + 4]) for index in range(words)]
    rcon = 1
    for index in range(words, 4 * (rounds + 1)):
        temp = list(schedule[index - 1])
        if index % words == 0:
            temp = temp[1:] + temp[:1]
            temp = [sbox[value] for value in temp]
            temp[0] ^= rcon
            rcon = _xtime(rcon)
        elif words > 6 and index % words == 4:
            temp = [sbox[value] for value in temp]
        schedule.append([schedule[index - words][j] ^ temp[j] for j in range(4)])
    return [bytes(sum(schedule[round * 4:round * 4 + 4], [])) for round in range(rounds + 1)], rounds


def _add_round_key(state, key):
    for index in range(BLOCK_SIZE):
        state[index] ^= key[index]


def _sub_bytes(state, box):
    for index in range(BLOCK_SIZE):
        state[index] = box[state[index]]


def _shift_rows(state, inverse=False):
    original = list(state)
    for row in range(1, 4):
        shift = (4 - row) if inverse else row
        for column in range(4):
            state[row + 4 * column] = original[row + 4 * ((column + shift) % 4)]


def _mix_columns(state, inverse=False):
    matrix = ((14, 11, 13, 9), (9, 14, 11, 13),
              (13, 9, 14, 11), (11, 13, 9, 14)) if inverse else \
             ((2, 3, 1, 1), (1, 2, 3, 1), (1, 1, 2, 3), (3, 1, 1, 2))
    for column in range(4):
        block = state[column * 4:column * 4 + 4]
        for row in range(4):
            state[column * 4 + row] = (
                _mul(block[0], matrix[row][0]) ^ _mul(block[1], matrix[row][1])
                ^ _mul(block[2], matrix[row][2]) ^ _mul(block[3], matrix[row][3]))


def encrypt_block(block, key):
    """Encrypt one 16-byte block; ``key`` may be 16, 24 or 32 bytes."""
    if len(block) != BLOCK_SIZE:
        raise ValueError("AES block must be 16 bytes")
    sbox, _ = _tables()
    schedule, rounds = _expand_key(key)
    state = bytearray(block)
    _add_round_key(state, schedule[0])
    for round in range(1, rounds):
        _sub_bytes(state, sbox)
        _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, schedule[round])
    _sub_bytes(state, sbox)
    _shift_rows(state)
    _add_round_key(state, schedule[rounds])
    return bytes(state)


def decrypt_block(block, key):
    """Decrypt one 16-byte block."""
    if len(block) != BLOCK_SIZE:
        raise ValueError("AES block must be 16 bytes")
    _, inverse = _tables()
    schedule, rounds = _expand_key(key)
    state = bytearray(block)
    _add_round_key(state, schedule[rounds])
    for round in range(rounds - 1, 0, -1):
        _shift_rows(state, inverse=True)
        _sub_bytes(state, inverse)
        _add_round_key(state, schedule[round])
        _mix_columns(state, inverse=True)
    _shift_rows(state, inverse=True)
    _sub_bytes(state, inverse)
    _add_round_key(state, schedule[0])
    return bytes(state)


def pad(data):
    """PKCS#7: always append 1..16 bytes."""
    amount = BLOCK_SIZE - len(data) % BLOCK_SIZE
    return data + bytes([amount]) * amount


def unpad(data):
    if not data or len(data) % BLOCK_SIZE:
        raise ValueError("padded data must be a non-empty multiple of 16 bytes")
    amount = data[-1]
    if not 1 <= amount <= BLOCK_SIZE or data[-amount:] != bytes([amount]) * amount:
        raise ValueError("invalid PKCS#7 padding")
    return data[:-amount]


def cbc_encrypt(data, key, iv, *, use_padding=True):
    if len(iv) != BLOCK_SIZE:
        raise ValueError("AES-CBC IV must be 16 bytes")
    buffer = bytearray(pad(data) if use_padding else data)
    if not buffer or len(buffer) % BLOCK_SIZE:
        raise ValueError("AES-CBC input must be a non-empty multiple of 16 bytes")
    previous = bytes(iv)
    for offset in range(0, len(buffer), BLOCK_SIZE):
        block = bytes(a ^ b for a, b in zip(buffer[offset:offset + BLOCK_SIZE], previous))
        previous = encrypt_block(block, key)
        buffer[offset:offset + BLOCK_SIZE] = previous
    return bytes(buffer)


def cbc_decrypt(data, key, iv, *, use_padding=True):
    if len(iv) != BLOCK_SIZE:
        raise ValueError("AES-CBC IV must be 16 bytes")
    if not data or len(data) % BLOCK_SIZE:
        raise ValueError("AES-CBC input must be a non-empty multiple of 16 bytes")
    buffer = bytearray(len(data))
    previous = bytes(iv)
    for offset in range(0, len(data), BLOCK_SIZE):
        block = data[offset:offset + BLOCK_SIZE]
        plain = decrypt_block(block, key)
        buffer[offset:offset + BLOCK_SIZE] = bytes(a ^ b for a, b in zip(plain, previous))
        previous = block
    return unpad(bytes(buffer)) if use_padding else bytes(buffer)
