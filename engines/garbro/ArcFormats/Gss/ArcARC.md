# Gss / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/LSD` / `GameRes.Formats.Gss.LsdOpener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LsdOpener.TryOpen` | `if (!bin.View.AsciiEqual (0, "LSDARC V.100"))` |
| `LsdOpener.TryOpen` | `int count = bin.View.ReadInt32 (0xC);` |
| `LsdOpener.TryOpen` | `entry.IsPacked     = index.ReadInt32() != 0;` |
| `LsdOpener.TryOpen` | `entry.Offset       = index.ReadUInt32();` |
| `LsdOpener.TryOpen` | `entry.UnpackedSize = index.ReadUInt32();` |
| `LsdOpener.TryOpen` | `entry.Size         = index.ReadUInt32();` |
| `LsdOpener.TryOpen` | `entry.Name         = index.ReadCString();` |
| `LsdOpener.OpenEntry` | `if (null == pent \|\| !pent.IsPacked \|\| !arc.File.View.AsciiEqual (entry.Offset, "LSD\x1A"))` |
| `LsdOpener.OpenEntry` | `byte enc_method = arc.File.View.ReadByte (entry.Offset+4);` |
| `LsdOpener.OpenEntry` | `byte pack_method = arc.File.View.ReadByte (entry.Offset+5);` |
| `LsdOpener.OpenEntry` | `uint unpacked_size = arc.File.View.ReadUInt32 (entry.Offset+6);` |
| `LsdOpener.UnpackD` | `var buf_packed = input.ReadBytes ((int)input.Length);` |
| `LsdOpener.UnpackD` | `v8 = BitConverter.ToInt32 (buf_packed, v7);` |
| `LsdOpener.UnpackD` | `v8 = BitConverter.ToInt32 (buf_packed, v7 + 1);` |
| `LsdOpener.UnpackD` | `v12 = BitConverter.ToInt32 (buf_packed, v11 + 3);` |
| `LsdOpener.UnpackD` | `v12 = BitConverter.ToInt32 (buf_packed, v11 + 2);` |
| `LsdOpener.UnpackD` | `v12 = BitConverter.ToInt32 (buf_packed, v11);` |
| `LsdOpener.UnpackD` | `v12 = BitConverter.ToInt32 (buf_packed, v11 + 1);` |
| `LsdOpener.UnpackR` | `int ctl = input.ReadByte();` |
| `LsdOpener.UnpackR` | `count = count << 8 \| input.ReadUInt8();` |
| `LsdOpener.UnpackR` | `byte v = input.ReadUInt8();` |
| `LsdOpener.UnpackH` | `var buf_packed = input.ReadBytes ((int)input.Length);` |
| `LsdOpener.UnpackH` | `ulong v25 = BitConverter.ToUInt32 (buf_packed, v24);` |
| `LsdOpener.UnpackH` | `while (BitConverter.ToUInt32 (buf, (int)off2 + 8 * v29) !=` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Gss.LsdOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly int[] dword_455540 = {
    0x0, 0x0, 0x0, 0x0, 0x3, 0x4, 0x5, 0x6,
    0x7, 0x8, 0x9, 0xA, 0xB, 0xC, 0xD, 0xE
}

static readonly int[] dword_455580 = {
    0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80,
    0x0100, 0x0200, 0x0400, 0x0800, 0x1000, 0x2000, 0x4000
}

static readonly int[] dword_4554E8 = {
    0x00, 0x00, 0x00, 0x00, 0x07, 0x0F, 0x1F, 0x3F,
    0x7F, 0xFF, 0x01FF, 0x03FF, 0x07FF, 0x0FFF, 0x1FFF, 0x3FFF
}

static readonly uint[] dword_8107F828 = {
    0x00, 0x00, 0x01, 0x00, 0x03, 0x00, 0x07, 0x00,
    0x0F, 0x00, 0x1F, 0x00, 0x3F, 0x00, 0x7F, 0x00,
    0xFF, 0x00, 0x01FF, 0x00, 0x03FF, 0x00, 0x07FF, 0x00,
    0x0FFF, 0x00, 0x1FFF, 0x00, 0x3FFF, 0x00, 0x7FFF, 0x00,
    0xFFFF, 0x00, 0x01FFFF, 0x00, 0x03FFFF, 0x00, 0x07FFFF, 0x00,
    0x0FFFFF, 0x00, 0x1FFFFF, 0x00, 0x3FFFFF, 0x00, 0x7FFFFF, 0x00,
    0xFFFFFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07, 0x0F,
    0x1F, 0x3F, 0x7F, 0xFF, 0x01FF, 0x03FF, 0x07FF, 0x0FFF,
    0x1FFF, 0x3FFF, 0x7FFF, 0xFFFF, 0x01FFFF, 0x03FFFF, 0x0FFFFF, 0x00,
    0x06050403, 0x0A090807, 0x0E0D0C0B, 0x00, 0x01, 0x02, 0x04, 0x08,
    0x10, 0x20, 0x40, 0x80, 0x0100, 0x0200, 0x0400, 0x0800,
    0x1000, 0x2000, 0x4000, 0x00, 0xFFFF0001, 0x00, 0x00, 0x01,
    0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0x01, 0x01
}

static readonly uint[] dword_8107F750 = {
    0x00, 0x00, 0x01, 0x03, 0x07, 0x0F, 0x1F, 0x3F,
    0x7F, 0xFF, 0x01FF, 0x03FF, 0x07FF, 0x0FFF, 0x1FFF, 0x3FFF,
    0x7FFF, 0xFFFF, 0x01FFFF, 0x03FFFF, 0x0FFFFF, 0x00, 0x00, 0x01
}

static readonly uint[] dword_8107F7A4 = {
    0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
    0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E,
    0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40,
    0x80, 0x0100, 0x0200, 0x0400, 0x0800, 0x1000, 0x2000, 0x4000,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x03, 0x00, 0x07,
    0x00, 0x0F, 0x00, 0x1F, 0x00, 0x3F, 0x00, 0x7F,
    0x00, 0xFF, 0x00, 0x01FF, 0x00, 0x03FF, 0x00, 0x07FF,
    0x00, 0x0FFF, 0x00, 0x1FFF, 0x00, 0x3FFF, 0x00, 0x7FFF,
    0x00, 0xFFFF, 0x00, 0x01FFFF, 0x00, 0x03FFFF, 0x00, 0x07FFFF,
    0x00, 0x0FFFFF, 0x00, 0x1FFFFF, 0x00, 0x3FFFFF, 0x00, 0x7FFFFF,
    0x00, 0xFFFFFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07,
    0x0F, 0x1F, 0x3F, 0x7F, 0xFF, 0x01FF, 0x03FF, 0x07FF,
    0x0FFF, 0x1FFF, 0x3FFF, 0x7FFF, 0xFFFF, 0x01FFFF, 0x03FFFF, 0x0FFFFF
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".arc"))
        return null;
    var bin_name = Path.ChangeExtension (file.Name, "BIN");
    if (!VFS.FileExists (bin_name))
        return null;
    using (var bin = VFS.OpenView (bin_name))
    {
        if (!bin.View.AsciiEqual (0, "LSDARC V.100"))
            return null;
        int count = bin.View.ReadInt32 (0xC);
        if (!IsSaneCount (count))
            return null;
        using (var index = bin.CreateStream())
        {
            index.Position = 0x10;
            var dir = new List<Entry> (count);
            for (int i = 0; i < count; ++i)
            {
                var entry = new PackedEntry();
                entry.IsPacked     = index.ReadInt32() != 0;
                entry.Offset       = index.ReadUInt32();
                entry.UnpackedSize = index.ReadUInt32();
                entry.Size         = index.ReadUInt32();
                entry.Name         = index.ReadCString();
                if (!entry.CheckPlacement (file.MaxOffset))
                    return null;
                dir.Add (entry);
            }
            return new ArcFile (file, this, dir);
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked || !arc.File.View.AsciiEqual (entry.Offset, "LSD\x1A"))
        return base.OpenEntry (arc, entry);
    byte enc_method = arc.File.View.ReadByte (entry.Offset+4);
    byte pack_method = arc.File.View.ReadByte (entry.Offset+5);
    uint unpacked_size = arc.File.View.ReadUInt32 (entry.Offset+6);
    using (var input = arc.File.CreateStream (entry.Offset+12, entry.Size-12))
    {
        var data = new byte[unpacked_size];
        int len;
        switch ((char)pack_method)
        {
        case 'D':   len = UnpackD (input, data); break;
        case 'R':   len = UnpackR (input, data); break;
        case 'H':   len = UnpackH (input, data); break;
        case 'W':   len = UnpackW (input, data); break;
        default:    len = input.Read (data, 0, data.Length); break;
        }
        len = Math.Min (len, data.Length);
        switch ((char)enc_method)
        {
        case 'N':
            break;
        case 'B':
            for (int i = 0; i < len; i++)
            {
                var d = data[i];
                var tmp = -d;
                if (i != 0)
                    tmp = data[i - 1] - d;
                data[i] = (byte)tmp;
            }
            break;
        case 'W':
            for (int i = 0; i < len; i += 2)
            {
                var d = data[i] | (data[i + 1] << 8);
                var tmp = -d;
                if (i != 0)
                    tmp = (data[i - 2] | data[i - 1] << 8) - d;
                data[i] = (byte)(tmp & 0xff);
                data[i + 1] = (byte)(tmp >> 8);
            }
            break;
        case 'S':
            for (int i = 0; i < len; i += 2)
            {
                var d = data[i + 1] | (data[i] << 8);
                var tmp = -d;
                if (i != 0)
                    tmp = (data[i - 1] | data[i - 2] << 8) - d;
                data[i] = (byte)(tmp >> 8);
                data[i + 1] = (byte)(tmp & 0xff);
            }
            break;
        }
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### UnpackD

```csharp
int UnpackD (IBinaryStream input, byte[] output) {
    var buf_packed = input.ReadBytes ((int)input.Length);
    int result = 0, i = 0, v8, v12;
    int v3 = 0, qword_811C97A8 = 0;
    var size1 = output.Length >> 1;
    byte v6, v16;
    if (size1 != 0)
    {
        int cur_output_addr = 0;
        int cur_pos = 0;
        do
        {
            v6 = (byte)(v3 & 0x1F);
            int v7 = (int)((v3 >> 3) & 0xFFFFFFFC);
            if ((int)(v3 & 0x1F) < 28)
            {
                v8 = BitConverter.ToInt32 (buf_packed, v7);
            }
            else
            {
                v8 = BitConverter.ToInt32 (buf_packed, v7 + 1);
                v6 -= (byte)8;
            }
            var v23 = v8 >> v6;
            qword_811C97A8 += 5;
            byte v10 = (byte)(qword_811C97A8 & 0x1F);
            int idx = v23 & 0xF;
            int v11 = (int)(((qword_811C97A8) >> 3) & 0xFFFFFFFC);
            if (v10 >= 24)
            {
                v12 = BitConverter.ToInt32 (buf_packed, v11 + 3);
                v16 = (byte)(v10 - 24);
            }
            else if (v10 >= 16)
            {
                v12 = BitConverter.ToInt32 (buf_packed, v11 + 2);
                v16 = (byte)(v10 - 16);
            }
            else
            {
                if (v10 < 8)
                {
                    v12 = BitConverter.ToInt32 (buf_packed, v11);
                }
                else
                {
                    v12 = BitConverter.ToInt32 (buf_packed, v11 + 1);
                    v10 -= 8;
                }
                v16 = v10;
            }
            var v19 = (dword_8107F750[idx] & (v12 >> v16)) + dword_8107F7A4[0x10 + idx];
            if ((v23 & 0x10) != 0)
                v19 = v19 & 0xffff0000 | (~v19 & 0xffff);
            output[cur_output_addr++] = (byte)(v19);
            output[cur_output_addr++] = (byte)(v19 >> 8);
            qword_811C97A8 += (int)dword_8107F7A4[idx];
            ++i;
            v3 = qword_811C97A8;
            cur_pos += 2;
        }
        while (i != size1);
        result = cur_pos + 2;
    }
    return result;
}
```

#### UnpackR

```csharp
int UnpackR (IBinaryStream input, byte[] output) {
    int dst = 0;
    while (dst < output.Length)
    {
        int ctl = input.ReadByte();
        if (-1 == ctl)
            break;
        int count;
        if ((ctl & 0xC0) == 0xC0)
        {
            count = ctl & 0xF;
            ctl &= 0xF0;
        }
        else
        {
            count = ctl & 0x3F;
            ctl &= 0xC0;
        }
        switch (ctl)
        {
        case 0xF0: return 0;
        case 0x40:
            input.Read (output, dst, count);
            dst += count;
            break;

        case 0xD0:
            count = count << 8 | input.ReadUInt8();
            input.Read (output, dst, count);
            dst += count;
            break;

        case 0x80:
            {
                byte v = input.ReadUInt8();
                while (count --> 0)
                    output[dst++] = v;
                break;
            }

        case 0xE0:
            {
                count = count << 8 | input.ReadUInt8();
                byte v = input.ReadUInt8();
                while (count --> 0)
                    output[dst++] = v;
                break;
            }

        case 0x00:
            dst += count;
            break;

        case 0xC0:
            count = count << 8 | input.ReadUInt8();
            dst += count;
            break;
        }
    }
    return dst;
}
```

#### UnpackH

```csharp
int UnpackH (IBinaryStream input, byte[] output) {
            var buf_packed = input.ReadBytes ((int)input.Length);
            var buf = new byte[0x10000];
            const uint off2 = 0x2004;
            const uint off3 = 0x2804;
            const uint off4 = 0x3004;

            uint cur_addr = 2, pre_pos, next_pos = 2, cur_output_addr = 0;
            byte outchar, i1 = 0, i2, v29, first_char = buf_packed[0];
            int idx1 = 0, v28 = 0;
            do
            {
                pre_pos = next_pos;
                var cur_char1 = buf_packed[cur_addr];
                var next_addr = cur_addr + 1;
                next_pos++;
                if (cur_char1 != 0)
                {
                    byte l1 = buf_packed[cur_addr + 1];
                    byte h1 = buf_packed[cur_addr + 2];
                    uint t1 = (ushort)(l1 + (h1 << 8));
                    if (cur_char1 >= 8)
                    {
                        if (cur_char1 >= 0xD)
                        {
                            uint d;
                            if (cur_char1 < 0x10)
                            {
                                d = t1;
                                next_addr = cur_addr + 3;
                                next_pos = pre_pos + 3;
                            }
                            else
                            {
                                d = (uint)(t1 + (buf_packed[cur_addr + 3] << 16));
                                next_addr = cur_addr + 4;
                                next_pos = pre_pos + 4;
                            }
                            buf[off3 + 4 + 8 * i1] = cur_char1;
                            BitConverter.GetBytes ((uint)(d)).CopyTo (buf, off3 + 8 * i1);
                            buf[off3 + 5 + 8 * i1] = (byte)idx1;
                            i1++;
                        }
                        else
                        {
                            buf[2 * t1] = (byte)idx1;
                            buf[2 * t1 + 1] = cur_char1;
                            next_addr = cur_addr + 3;
                            next_pos = pre_pos + 3;
                        }
                    }
                    else
                    {
                        buf[2 * l1] = (byte)idx1;
                        buf[2 * l1 + 1] = cur_char1;
                        next_addr = cur_addr + 2;
                        next_pos = pre_pos + 2;
                    }
                }
                cur_addr = next_addr;
                ++idx1;
            } while (idx1 != 0x100);

            byte idx2 = 0;
            byte v19 = 0xD;
            do
            {
                i2 = 0;
                buf[off4 + v19] = (byte)idx2;
                if (i1 != 0)
                {
                    int buf3_addr = 0x2804;
                    do
                    {
                        if (buf[buf3_addr + 4] == v19)
                        {
                            Array.Copy (buf, buf3_addr, buf, off2 + 8 * idx2, 4);
                            Array.Copy (buf, buf3_addr+4, buf, off2 + 4 + 8 * idx2, 4);
                            idx2++;
                        }
                        ++i2;
                        buf3_addr += 8;
                    }
                    while (i2 != i1);
                }
                v19++;
            } while (v19 != 0x18);

            buf[0x301c] = (byte)idx2;
            Array.Clear (buf, 0x3028, 8);
            int v23 = (int)output.Length, v33 = 0, size_done = 0;
            while (true)
            {
                int v24 = (int)(next_pos + ((uint)(v33 & 0x1F) >> 3) + ((v33 >> 3) & 0xFFFFFFFC));
                ulong v25 = BitConverter.ToUInt32 (buf_packed, v24);
                byte cur_char2 = first_char;
                uint a3 = (uint)((v33 & 0x1F) - (v33 & 0x18));
                uint v27 = (uint)v25;
                if (a3 > 63)
                    v27 = 0;
                else if (a3 != 0)
                    v27 = (uint)(v25 >> (int)a3);
                if (first_char != 0xD)
                {
                    while (true)
                    {
                        v28 = (int)(v27 & dword_8107F828[2 * cur_char2]);
                        BitConverter.GetBytes ((int)(2 * v28 + 0x811C6780)).CopyTo (buf, off2 - 4);
                        if (cur_char2 == buf[2 * v28 + 1])
                            break;
                        cur_char2++;
                        if (cur_char2 == 0xD)
                            goto LABEL_22;
                    }
                    outchar = buf[2 * v28];
                    goto LABEL_29;
                }
LABEL_22:
                if (cur_char2 == 0x18)
                    break;
LABEL_26_2:
                while (true)
                {
                    v29 = buf[off4 + cur_char2];
                    if (v29 != buf[off4 + 1 + cur_char2])
                        break;
                    if (++cur_char2 == 0x18)
                    {
                        return 0;

                    }
                }
                while (BitConverter.ToUInt32 (buf, (int)off2 + 8 * v29) !=
                       (v27 & dword_8107F828[2 * cur_char2]))
                {
                    v29++;
                    if (v29 == buf[off4 + 1 + cur_char2 ])
                    {
                        if (++cur_char2 == 0x18)
                        {
                            return 0;
                        }
                        goto LABEL_26_2;
                    }
                }
                outchar = buf[off2 + 5 + 8 * v29];
LABEL_29:
                output[cur_output_addr] = (byte)outchar;
                BitConverter.GetBytes ((Int64)v33 + (ushort)cur_char2).CopyTo (buf, 0x3028);
                v23 = size_done + 1;
                ++cur_output_addr;
                v33 += cur_char2 ;
                size_done = v23;
                if (v23 >= output.Length)
                    return size_done;
            }
            return 0;
        }
```

#### UnpackW

```csharp
int UnpackW (IBinaryStream input, byte[] output) {
    throw new NotImplementedException();

}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Gss/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
