# SPDX-License-Identifier: MIT
"""ERISA-N ("Nemesis") decompression and BSHF decryption used by Entis NOA members.

Ported from GARbro (MIT, Copyright (C) 2015-2018 by morkt; C# port of the ERISA
library, Copyright (C) 2002-2007 Leshade Entis, Entis-soft):
  ArcFormats/Entis/ErisaNemesis.cs  NemesisDecodeContext.DecodeNemesisCodeBytes,
                                    ErisaProbBase, Nemesis, NemesisPhraseLookup
  ArcFormats/Entis/EriReader.cs     ProbDecodeContext.DecodeERISACodeIndex /
                                    InitializeERISACode, ErisaProbModel
  ArcFormats/Entis/ArcNOA.cs        ERISADecodeContext bit reader, BSHFDecodeContext,
                                    ERIBshfBuffer.DecodeBuffer
Bundled algorithm notes: engines/garbro/ArcFormats/Entis/{ErisaNemesis,EriReader,ArcNOA}.md.

Differences from the reference: whole-buffer decoding instead of a stream; the
decoder raises when the output budget, step budget or model capacity is exceeded
or when fewer than ``size`` bytes can be produced, instead of returning a short
stream. Pure decoding: no compressor is provided.
"""

from ..common.binary import FormatError

TOTAL_LIMIT = 0x2000
SYMBOL_SORT_MAX = 0x101
SUB_SORT_MAX = 0x80
SLOT_MAX = 0x800
ESC = -1
BUF_MASK = 0xFFFF
INDEX_MASK = 0xFF
SHIFT_COUNT = (1, 3, 4, 5)
NEW_PROB_LIMIT = (0x01, 0x08, 0x10, 0x20)
MAX_OUTPUT = 256 * 1024 * 1024
M32 = 0xFFFFFFFF


class _Model:
    """ErisaProbModel; ``occ``/``sym`` are the parallel CodeSymbol table."""

    __slots__ = ("total", "sorts", "occ", "sym", "sub_occ", "sub_sym")

    def __init__(self, initialize=True):
        if initialize:
            self.total = SYMBOL_SORT_MAX
            self.sorts = SYMBOL_SORT_MAX
            self.occ = [1] * SYMBOL_SORT_MAX
            self.sym = list(range(0x100)) + [ESC]
        else:                      # a fresh C# object: everything zero
            self.total = 0
            self.sorts = 0
            self.occ = [0] * SYMBOL_SORT_MAX
            self.sym = [0] * SYMBOL_SORT_MAX
        self.sub_occ = [0] * SUB_SORT_MAX
        self.sub_sym = [-1] * SUB_SORT_MAX if initialize else [0] * SUB_SORT_MAX

    def increase(self, index):
        occ, sym = self.occ, self.sym
        value = occ[index] + 1
        symbol = sym[index]
        while index > 0 and occ[index - 1] < value:
            occ[index] = occ[index - 1]
            sym[index] = sym[index - 1]
            index -= 1
        occ[index] = value
        sym[index] = symbol
        self.total += 1
        if self.total >= TOTAL_LIMIT:
            total = 0
            for i in range(self.sorts):
                occ[i] = (occ[i] + 1) >> 1
                total += occ[i]
            self.total = total
            sub = self.sub_occ
            for i in range(SUB_SORT_MAX):
                sub[i] >>= 1
        return index

    def add(self, symbol):
        if self.sorts >= SYMBOL_SORT_MAX:
            raise FormatError("ERISA model symbol table overflow")
        self.occ[self.sorts] = 1
        self.sym[self.sorts] = symbol
        self.sorts += 1
        self.total += 1


def decode_nemesis(data, size, *, max_output=MAX_OUTPUT):
    """Decode an ERISA-N stream to exactly ``size`` bytes or raise FormatError.

    ``size=None`` decodes until the stream's explicit end code (used for embedded
    resources whose length is not stored); ``max_output`` still bounds the result.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise FormatError("ERISA-N input must be bytes")
    if type(max_output) is not int or max_output < 0:
        raise FormatError("invalid ERISA-N output budget")
    until_end = size is None
    if until_end:
        size = max_output
    elif type(size) is not int or size < 0:
        raise FormatError("invalid ERISA-N output size")
    elif size > max_output:
        raise FormatError("ERISA-N output exceeds budget")
    if size == 0:
        return b""
    ended = False
    data = bytes(data)
    # Bit source: MSB-first over the input zero padded to whole 32-bit words.
    stream = data + b"\0" * (-len(data) % 4)
    total_bits = len(stream) * 8
    first = min(32, total_bits)
    code = int.from_bytes(stream[:first // 8], "big")
    bitpos = first                 # next bit to read
    augend = 0xFFFF
    post = 0

    phrase_len = _Model()
    phrase_index = _Model()
    run_len = _Model()
    base = _Model()
    slots = []                     # ptrProbIndex, allocated on use (dwWorkUsed = len)
    last = [0, 0, 0, 0]
    ilast = 0
    nbuf = bytearray(BUF_MASK + 1)
    nidx = 0
    lookup_first = [0] * 256
    lookup_index = [[0] * 256 for _ in range(256)]
    out = bytearray()
    left = 0
    nnext = -1
    steps = 0
    step_limit = 4 * size + 4096

    def decode_index(model):
        nonlocal code, augend, bitpos, post
        total = model.total
        if total == 0:
            raise FormatError("invalid Nemesis encoding sequence")
        acc = ((code * total) & M32) // augend
        if acc >= TOTAL_LIMIT:
            return -1
        occ = model.occ
        sorts = model.sorts
        i = 0
        fs = 0
        while True:
            o = occ[i]
            if acc < o:
                break
            acc -= o
            fs += o
            i += 1
            if i >= sorts:
                return -1
        code = (code - (augend * fs + total - 1) // total) & M32
        augend = augend * o // total
        if augend == 0:
            raise FormatError("invalid Nemesis encoding sequence")
        while not augend & 0x8000:
            if bitpos < total_bits:
                bit = (stream[bitpos >> 3] >> (7 - (bitpos & 7))) & 1
                bitpos += 1
            else:
                post += 1
                if post >= 256:
                    return -1
                bit = 0
            code = ((code << 1) | bit) & M32
            augend <<= 1
        code &= 0xFFFF
        return i

    def decode_code(model):
        i = decode_index(model)
        if i < 0:
            return ESC
        symbol = model.sym[i]
        model.increase(i)
        return symbol

    def emit(symbol):
        nonlocal ilast, nidx
        last[ilast] = symbol
        ilast = (ilast + 1) & 3
        f = lookup_first[symbol]
        lookup_index[symbol][f] = nidx
        lookup_first[symbol] = (f + 1) & INDEX_MASK
        nbuf[nidx] = symbol
        nidx = (nidx + 1) & BUF_MASK
        out.append(symbol)

    while len(out) < size:
        steps += 1
        if steps > step_limit:
            raise FormatError("ERISA-N step budget exceeded")
        if left > 0:
            count = min(left, size - len(out))
            symbol = nbuf[(nidx - 1) & BUF_MASK]
            for _ in range(count):
                if nnext >= 0:
                    symbol = nbuf[nnext]
                    nnext = (nnext + 1) & BUF_MASK
                emit(symbol)
            left -= count
            continue

        model = base
        deg = 0
        while deg < 4:
            sub = last[(ilast + 3 - deg) & 3] >> SHIFT_COUNT[deg]
            slot = model.sub_sym[sub]
            if slot < 0:
                break
            if slot >= len(slots):
                raise FormatError("invalid Nemesis encoding sequence")
            model = slots[slot]
            deg += 1
        i = decode_index(model)
        if i < 0:
            break
        symbol = model.sym[i]
        model.increase(i)

        nemesis = False
        if symbol == ESC:
            if model is not base:
                i = decode_index(base)
                if i < 0:
                    break
                symbol = base.sym[i]
                base.increase(i)
                if symbol != ESC:
                    model.add(symbol)
                else:
                    nemesis = True
            else:
                nemesis = True
        if nemesis:
            index = decode_code(phrase_index)
            if index == ESC:
                ended = True                       # explicit end of stream
                break
            length = decode_code(run_len if index == 0 else phrase_len)
            if length == ESC:
                break
            prev = nbuf[(nidx - 1) & BUF_MASK]
            left = length
            if index == 0:
                nnext = -1
            else:
                nnext = lookup_index[prev][(lookup_first[prev] - index) & INDEX_MASK]
                if nbuf[nnext] != prev:
                    raise FormatError("invalid Nemesis encoding sequence")
                nnext = (nnext + 1) & BUF_MASK
            continue

        emit(symbol)
        if len(slots) < SLOT_MAX and deg < 4:
            sub = symbol >> SHIFT_COUNT[deg]
            if sub >= SUB_SORT_MAX:
                raise FormatError("invalid Nemesis encoding sequence")
            model.sub_occ[sub] += 1
            if model.sub_occ[sub] >= NEW_PROB_LIMIT[deg]:
                parent = model
                model = base
                k = 0
                while k <= deg:
                    sub = last[(ilast + 3 - k) & 3] >> SHIFT_COUNT[k]
                    slot = model.sub_sym[sub]
                    if slot < 0:
                        break
                    if slot >= len(slots):
                        raise FormatError("invalid Nemesis encoding sequence")
                    model = slots[slot]
                    k += 1
                if k <= deg and model.sub_sym[sub] < 0:
                    fresh = _Model(initialize=False)
                    model.sub_sym[sub] = len(slots)
                    slots.append(fresh)
                    j = 0
                    total = 0
                    for t in range(parent.sorts):
                        occurred = parent.occ[t] >> 4
                        if occurred > 0 and parent.sym[t] != ESC:
                            total += occurred
                            fresh.occ[j] = occurred
                            fresh.sym[j] = parent.sym[t]
                            j += 1
                    fresh.occ[j] = 1
                    fresh.sym[j] = ESC
                    fresh.sorts = j + 1
                    fresh.total = total + 1
                    fresh.sub_occ = [0] * SUB_SORT_MAX
                    fresh.sub_sym = [-1] * SUB_SORT_MAX
    if until_end:
        if not ended:
            raise FormatError("ERISA-N stream has no end code within the output budget")
        return bytes(out)
    if len(out) != size:
        raise FormatError(f"ERISA-N stream ended after {len(out)} of {size} bytes")
    return bytes(out)


def _bshf_password(password):
    if not password:
        password = " "
    try:
        raw = bytearray(password.encode("ascii"))
    except UnicodeEncodeError as exc:
        raise FormatError("BSHF password must be ASCII") from exc
    if len(raw) < 32:
        raw.append(0x1B)
        count = len(raw)
        while len(raw) < 32:
            i = len(raw)
            raw.append((raw[i % count] + raw[i - 1]) & 0xFF)
    return bytes(raw)


def decode_bshf(data, password, *, max_output=MAX_OUTPUT):
    """BSHFDecodeContext: 32-byte bit-shuffle blocks keyed by an ASCII password.

    The reference decodes ``len(data) - 4`` bytes and needs whole 32-byte blocks to
    cover them; the final partial block, if any, is rejected.
    """
    data = bytes(data)
    if len(data) < 4:
        raise FormatError("BSHF payload too short")
    want = len(data) - 4
    if want > max_output:
        raise FormatError("BSHF output exceeds budget")
    blocks = (want + 31) // 32
    if blocks * 32 > len(data):
        raise FormatError("BSHF payload ends inside a block")
    key = _bshf_password(password)
    plen = len(key)
    offset = 0
    out = bytearray()
    for b in range(blocks):
        src = data[b * 32:b * 32 + 32]
        if offset >= plen:
            offset = 0
        buf = bytearray(32)
        mask = bytearray(32)
        pos = offset
        offset += 1
        bit = 0
        for i in range(256):
            bit = (bit + key[pos]) & 0xFF
            pos += 1
            if pos >= plen:
                pos = 0
            off = bit >> 3
            m = 0x80 >> (bit & 7)
            while mask[off] == 0xFF:
                bit = (bit + 8) & 0xFF
                off = bit >> 3
            while mask[off] & m:
                bit += 1
                m >>= 1
                if m == 0:
                    bit = (bit + 8) & 0xFF
                    off = bit >> 3
                    m = 0x80
            mask[off] |= m
            if src[i >> 3] & (0x80 >> (i & 7)):
                buf[off] |= m
        out += buf
    return bytes(out[:want])
