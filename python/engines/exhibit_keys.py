"""Static ExHibit v3 key recovery from inert PE bytes and ExHIBIT.ini.

RT_BITMAP/152 blue LSBs XOR the protected INI checksum produce the scenario
seed. The def seed is recovered from bounded x86 immediate-store candidates,
validated by decrypting and completely parsing def.rld. No DLL is loaded.
"""
import configparser
import re
import struct

from .exhibit_rld import crypt, parse


class PE:
    def __init__(self, data):
        if len(data) > 128 << 20:
            raise ValueError("PE input exceeds budget")
        self.data = data
        if self.take(0, 2) != b"MZ":
            raise ValueError("not PE")
        pe = self.u32(0x3C)
        if self.take(pe, 4) != b"PE\0\0":
            raise ValueError("invalid PE signature")
        self.machine = self.u16(pe + 4)
        count, size = self.u16(pe + 6), self.u16(pe + 20)
        opt = pe + 24
        magic = self.u16(opt)
        directory = {0x10B: 96, 0x20B: 112}.get(magic)
        if directory is None or size < directory or not 0 < count <= 96:
            raise ValueError("unsupported PE header")
        self.take(opt, size)
        n = min(self.u32(opt + directory - 4), (size - directory) // 8)
        self.resource = (self.u32(opt + directory + 16), self.u32(opt + directory + 20)) if n >= 3 else (0, 0)
        self.sections = []
        for i in range(count):
            at = opt + size + i * 40
            self.take(at, 40)
            va, length, raw, flags = self.u32(at + 12), self.u32(at + 16), self.u32(at + 20), self.u32(at + 36)
            self.take(raw, length)
            self.sections.append((va, length, raw, flags))

    def take(self, at, size):
        if at < 0 or size < 0 or at + size > len(self.data):
            raise ValueError("PE offset outside file")
        return self.data[at:at + size]

    def u16(self, at):
        return struct.unpack("<H", self.take(at, 2))[0]

    def u32(self, at):
        return struct.unpack("<I", self.take(at, 4))[0]

    def rva(self, address, size):
        hits = [raw + address - va for va, length, raw, _ in self.sections
                if va <= address and address + size <= va + length]
        if len(hits) != 1:
            raise ValueError("unmapped/ambiguous PE RVA")
        self.take(hits[0], size)
        return hits[0]

    def bitmap(self, resource_id=152):
        address, size = self.resource
        if not 0 < size <= 16 << 20:
            raise ValueError("missing/oversized PE resources")
        base = self.rva(address, size)

        def rel(at, length):
            if at < 0 or at + length > size:
                raise ValueError("PE resource outside directory")
            return base + at

        def children(offset):
            at = rel(offset, 16)
            count = self.u16(at + 12) + self.u16(at + 14)
            if count > 4096:
                raise ValueError("PE resource entry limit")
            rel(offset + 16, count * 8)
            return [(self.u32(at + 16 + i * 8), self.u32(at + 20 + i * 8)) for i in range(count)]

        def directory(offset, key):
            hits = [v for k, v in children(offset) if k == key]
            if len(hits) != 1 or not hits[0] & 0x80000000:
                raise ValueError("missing/ambiguous bitmap resource directory")
            return hits[0] & 0x7FFFFFFF

        blobs = []
        for _, target in children(directory(directory(0, 2), resource_id)):
            if target & 0x80000000:
                raise ValueError("unexpected bitmap resource depth")
            at = rel(target, 16)
            rva, length = self.u32(at), self.u32(at + 4)
            if not 0 < length <= 16 << 20 or not address <= rva or rva + length > address + size:
                raise ValueError("bitmap outside resource region")
            blobs.append(self.take(self.rva(rva, length), length))
        if not blobs or any(blob != blobs[0] for blob in blobs):
            raise ValueError("missing/conflicting bitmap languages")
        return blobs[0]


def bitmap_bits(dib):
    if len(dib) < 40:
        raise ValueError("truncated bitmap")
    size, width, height, planes, bpp, compression = struct.unpack_from("<IiiHHI", dib)
    if size != 40 or planes != 1 or bpp not in (24, 32) or compression != 0:
        raise ValueError("expected uncompressed BITMAPINFOHEADER 24/32-bit bitmap")
    if struct.unpack_from("<I", dib, 32)[0] != 0:
        raise ValueError("bitmap color tables are outside this profile")
    # Stored row order is part of this profile. Top-down DIBs need a separately
    # verified conversion; do not silently reverse their bits.
    if not 32 <= width <= 8192 or not 32 <= height <= 8192:
        raise ValueError("unsupported bitmap dimensions/orientation")
    stride = ((width * bpp + 31) // 32) * 4
    if len(dib) < 40 + stride * height:
        raise ValueError("truncated bitmap pixels")
    value = 0
    for row in range(height - 32, height):
        value = (value << 1) | (dib[40 + row * stride + 31 * (bpp // 8)] & 1)
    return value


def ini_checksum(raw):
    if len(raw) > 1 << 20:
        raise ValueError("INI exceeds budget")
    ini = configparser.ConfigParser(interpolation=None, strict=True)
    ini.read_string(raw.decode("cp932", "strict"))
    sections = [name for name in ini.sections() if name.casefold() == "setting"]
    if len(sections) != 1 or ini.defaults():
        raise ValueError("missing/ambiguous INI setting section or unsupported DEFAULT")
    setting = ini[sections[0]]

    def number(key, default):
        text = setting.get(key, str(default))
        if not re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[+-]?[0-9]+)", text):
            raise ValueError(f"unsupported INI numeric syntax: {key}")
        return int(text, 16 if text.lower().startswith("0x") else 10)

    fields = ["CLASS"]
    if number("SYSVER", 0) < 1:
        fields.append("TITLE")
    fields.extend(("W_VIEW", "H_VIEW", "N_REG", "N_STRREG", "N_SYSREG", "N_LOCREG",
                   "N_USAVE", "N_ASAVE", "N_QSAVE", "N_CG", "N_MESSAGE", "N_SCENE", "N_SOUND"))
    if number("FLAGS", 0) & 4:
        fields.extend(("FLAGS", "GUID", "SVDATA"))
    values = []
    for field in fields:
        text = setting.get(field, "")
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            text = text[1:-1]  # GetPrivateProfileString strips matching quotes.
        if "\n" in text or "\r" in text:
            raise ValueError("multiline protected INI value")
        values.append(text.encode("cp932", "strict"))
    data = b"".join(values)
    return sum((sum(data[lane::4]) & 255) << (8 * lane) for lane in range(4))


def scenario_seed(exe, ini):
    pe = PE(exe)
    bits, checksum = bitmap_bits(pe.bitmap()), ini_checksum(ini)
    return bits ^ checksum, {"method": "bitmap152-blue-lsb-xor-ini", "bitmap_bits": bits,
                             "ini_checksum": checksum, "machine": pe.machine}


def recover_def_seed(resident, encrypted):
    """Test bounded x86 C7 /0 [reg+disp32],imm32 candidates; require one match."""
    pe = PE(resident)
    if pe.machine != 0x14C:
        raise ValueError("automatic def seed recovery requires x86 resident PE")
    candidates = {0}
    for _, size, raw, flags in pe.sections:
        if not flags & 0x20000000:
            continue
        code = pe.take(raw, size)
        # SIB form included, as well as the simpler disp32 addressing form.
        for pattern in (rb"\xc7[\x80-\x83\x85-\x87].{8}", rb"\xc7\x84.{9}"):
            for match in re.finditer(b"(?=(" + pattern + b"))", code, re.DOTALL):
                candidates.add(struct.unpack("<I", match.group(1)[-4:])[0])
                if len(candidates) > 20000:
                    raise ValueError("def seed candidate budget exceeded; provide --def-seed")
    matches = []
    for seed in sorted(candidates):
        try:
            prefix = crypt(encrypted[:276], seed)
            count, = struct.unpack_from("<I", prefix, 16)
            tag = prefix[20:276].split(b"\0", 1)[0].decode("cp932", "strict")
            if count != (len(tag.split(",")) if tag else 0):
                continue
            parse(crypt(encrypted, seed))
        except (ValueError, UnicodeError, struct.error):
            continue
        matches.append(seed)
    if len(matches) != 1:
        raise ValueError(f"def seed recovery found {len(matches)} validated matches; provide --def-seed")
    return matches[0], {"method": "x86-immediate-store-full-rld-validation", "candidates": len(candidates)}
