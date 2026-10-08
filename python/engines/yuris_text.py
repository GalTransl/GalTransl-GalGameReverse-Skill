# SPDX-License-Identifier: GPL-3.0-only
"""YU-RIS v482 scenario attribute writer with append-only text replacement.

Descriptor layout: VNTextPatch-net8 YurisAttribute.cs (MIT, d9c0fab7b72fdcf87d674ef12a84d3829c9188be).
Command/selection semantics cross-checked with SExtractor and msg-tool (GPLv3).
No VM execution: opaque attributes retain their bytes and original pool offsets.
"""
from dataclasses import dataclass
import re
import struct
from .yuris import toggle_ybn_sections, read_command_list, convert_control_bytes
from ..common.contract import make_manifest, validate_translation


@dataclass(frozen=True)
class Profile:
    key: int = 0x96AC6FD3
    source_characters: str = ""
    target_characters: str = ""

    def __post_init__(self):
        a, b = self.source_characters, self.target_characters
        if len(a) != len(b) or len(set(a)) != len(a) or len(set(b)) != len(b):
            raise ValueError("substitution table must be bijective")

    def display(self, text):
        return text.translate(str.maketrans(self.source_characters, self.target_characters))

    def encode(self, text):
        stored = text.translate(str.maketrans(self.target_characters, self.source_characters))
        data = stored.encode("cp932", "strict")
        if self.display(data.decode("cp932", "strict")) != text:
            raise ValueError("text cannot be represented by the existing character mapping")
        return data

    def settings(self):
        return {"key": self.key, "source_characters": self.source_characters,
                "target_characters": self.target_characters}


class Scenario:
    def __init__(self, raw, commands, key):
        if len(raw) > 64 << 20 or raw[:4] != b"YSTB" or struct.unpack_from("<I", raw, 4)[0] != 482:
            raise ValueError("expected bounded v482 YSTB")
        self.plain = toggle_ybn_sections(raw, key)
        self.key = key
        self.literal_eval = any(name == "_" and attrs and attrs[0][1] == b"\x03\0"
                                for name, attrs in commands)
        self.sizes = struct.unpack_from("<IIII", raw, 12)
        cs, ds, vs, ls = self.sizes
        if ds % 12 or ls != cs:
            raise ValueError("descriptor or line-number section mismatch")
        self.desc_start, self.value_start = 32 + cs, 32 + cs + ds
        self.values = self.plain[self.value_start:self.value_start + vs]
        self.attrs = list(struct.iter_unpack("<HHII", self.plain[self.desc_start:self.value_start]))
        self.instructions, cursor, self.control_targets = [], 0, set()
        for code, count, flags in struct.iter_unpack("<BBH", self.plain[32:self.desc_start]):
            if code >= len(commands) or cursor + count > len(self.attrs):
                raise ValueError("unknown command or attribute count")
            for i in range(cursor, cursor + count):
                aid, typ, size, offset = self.attrs[i]
                # IF/ELSE/LOOP raw pseudo-attributes contain an instruction
                # target and pool cursor, NOT a byte string length+offset.
                if commands[code][0] in ("IF", "ELSE", "LOOP") and typ == 0 and i > cursor:
                    if size > cs // 4 or offset > vs:
                        raise ValueError("invalid control-flow target")
                    self.control_targets.add(i)
                elif (typ & 255) > 4 or (typ >> 8) > 8 or offset + size > vs:
                    raise ValueError("invalid attribute type/range (check key and YSCM)")
                # LET/declaration instructions reuse ID 0. It is not a unique
                # key; retain descriptors by occurrence, including type flags.
            self.instructions.append((commands[code][0], tuple(range(cursor, cursor + count))))
            cursor += count
        if cursor != len(self.attrs):
            raise ValueError("unconsumed descriptors")

    def value(self, number):
        if number in self.control_targets:
            raise ValueError("control-flow target is not an attribute value")
        _, _, size, offset = self.attrs[number]
        return self.values[offset:offset + size]

    def serialize(self, changes):
        if set(changes) - set(range(len(self.attrs))) or set(changes) & self.control_targets:
            raise ValueError("unknown changed descriptor")
        prefix = bytearray(self.plain[:self.value_start])
        values = bytearray(self.values)
        for number, value in sorted(changes.items()):
            if not isinstance(value, bytes) or len(value) > 16 << 20:
                raise ValueError("invalid attribute payload")
            if value == self.value(number):
                continue
            if len(values) + len(value) > 64 << 20:
                raise ValueError("value pool exceeds budget")
            struct.pack_into("<II", prefix, self.desc_start + number * 12 + 4, len(value), len(values))
            values.extend(value)
        struct.pack_into("<I", prefix, 20, len(values))
        # Every original pool offset and the entire line-number table survive.
        plain = bytes(prefix) + bytes(values) + self.plain[self.value_start + len(self.values):]
        return toggle_ybn_sections(plain, self.key)


def commands_from(ysc):
    if len(ysc) > 1 << 20:
        raise ValueError("YSCM exceeds budget")
    commands = read_command_list(ysc, allow_message_tail=True)
    if struct.unpack_from("<I", ysc, 4)[0] != 482:
        raise ValueError("YSCM version mismatch")
    return commands


def literal(value):
    if len(value) < 5 or value[0] != 0x4D or struct.unpack_from("<H", value, 1)[0] != len(value) - 3:
        return None
    # These delimiters are observed in native and already-patched scripts.
    if value[3] not in b"\"'`" or value[-1] != value[3]:
        raise ValueError("unsupported expression string delimiters")
    return value[4:-1].decode("cp932", "strict")


def _rows(scenario, profile):
    rows, locations = [], []
    for instruction, (command, attributes) in enumerate(scenario.instructions):
        selected = []
        if command == "WORD":
            if len(attributes) != 1 or scenario.attrs[attributes[0]][1] != 0:
                raise ValueError("unsupported WORD attribute layout")
            selected = [(attributes[0], "dialogue")]
        elif command == "_":
            if any(scenario.value(a) for a in attributes):
                if (not scenario.literal_eval or len(attributes) != 1
                        or scenario.attrs[attributes[0]][1] != 3
                        or literal(scenario.value(attributes[0])) is None):
                    raise ValueError("dynamic EVAL needs expression/grouping support")
                selected = [(attributes[0], "literal-dialogue")]
        elif command == "GOSUB" and attributes:
            target = literal(scenario.value(attributes[0]))
            if target and target.lower() in ("es.char.name", "es.sel.set"):
                if scenario.attrs[attributes[0]][:2] != (0, 3):
                    raise ValueError("unsupported visible GOSUB target layout")
                if target.lower() == "es.char.name":
                    if (len(attributes) < 3 or scenario.attrs[attributes[1]][0] != 33
                            or scenario.attrs[attributes[2]][0] != 34):
                        raise ValueError("unsupported ES.CHAR.NAME parameter layout")
                    parameters, role = attributes[2:3], "name-definition"
                else:
                    parameters, role = attributes[1:], "choice"
                for number in parameters:
                    aid, typ, _, _ = scenario.attrs[number]
                    if 33 <= aid <= 48:
                        if typ != 3:
                            raise ValueError("unsupported visible GOSUB parameter type")
                        value = literal(scenario.value(number))
                        if value is None:
                            raise ValueError("dynamic visible GOSUB parameter")
                        if not value and role == "choice":
                            break
                        selected.append((number, role))
        for number, role in selected:
            raw = scenario.value(number)
            if not raw:
                continue
            if role == "dialogue":
                value = convert_control_bytes(raw).decode("cp932", "strict").replace("\r\n", "\n")
            else:
                value = literal(raw)
                if value is None or "\\" in value:
                    raise ValueError("unsupported escaped expression literal")
            value = profile.display(value)
            if not value:
                continue
            row = {"message": value}
            loc = {"instruction": instruction, "attribute": number, "role": role,
                   "offset": scenario.attrs[number][3], "length": len(raw)}
            match = re.fullmatch(r'【([^】]+)】(.*)', value, re.S)
            if role in ("dialogue", "literal-dialogue") and match:
                row = {"name": match[1], "message": match[2]}
                loc["name_wrapper"] = "【】"
            rows.append(row)
            locations.append(loc)
    return rows, locations


def export_script(raw, ysc, profile=Profile()):
    s = Scenario(raw, commands_from(ysc), profile.key)
    rows, locations = _rows(s, profile)
    manifest = make_manifest(engine="yuris", variant="482-word-raw", reference="yuris_text/2",
                             sources={"member.ybn": raw, "ysc.ybn": ysc}, rows=rows, locators=locations,
                             encoding="utf-8", settings=profile.settings(),
                             name_policies=["writable" if "name" in r else "absent" for r in rows])
    return rows, manifest


def rebuild_script(raw, ysc, translated, manifest, profile=Profile()):
    commands = commands_from(ysc)
    scenario = Scenario(raw, commands, profile.key)
    rows, locations = _rows(scenario, profile)
    _, expected = export_script(raw, ysc, profile)
    if manifest != expected:
        raise ValueError("manifest differs from reparsed original")
    translated = validate_translation(manifest, {"member.ybn": raw, "ysc.ybn": ysc}, rows, translated)
    changes = {}
    for before, after, location in zip(rows, translated, locations):
        if before == after:
            continue
        for field in before:
            if "\0" in after[field] or "\r" in after[field]:
                raise ValueError("NUL/CR in translated text")
            if re.findall(r'\\[pcu]|\n', before[field]) != re.findall(r'\\[pcu]|\n', after[field]):
                raise ValueError("control-code order/count changed")
        if "name" in after and (not after["name"] or any(c in after["name"] for c in "【】\n")):
            raise ValueError("invalid speaker name")
        value = ("【" + after["name"] + "】" if "name" in after else "") + after["message"]
        if location["role"] == "dialogue":
            data = convert_control_bytes(profile.encode(value.replace("\n", "\r\n")), to_yuris=True)
        else:
            if any(c in value for c in "\\\n"):
                raise ValueError("unsupported expression escaping")
            inner = profile.encode(value)
            delimiter = next((c for c in b"\"'`" if c not in inner), None)
            if delimiter is None or len(inner) + 2 > 65535:
                raise ValueError("expression literal is too long or has no safe delimiter")
            data = b"M" + struct.pack("<H", len(inner) + 2) + bytes([delimiter]) + inner + bytes([delimiter])
        changes[location["attribute"]] = data
    result = scenario.serialize(changes)
    check = Scenario(result, commands, profile.key)
    actual, _ = _rows(check, profile)
    if actual != translated:
        raise ValueError("reparsed translation differs")
    for i in range(len(scenario.attrs)):
        if i in scenario.control_targets:
            if check.attrs[i] != scenario.attrs[i]:
                raise ValueError("control-flow target changed")
            continue
        if check.value(i) != changes.get(i, scenario.value(i)):
            raise ValueError("non-target attribute changed")
    return result
