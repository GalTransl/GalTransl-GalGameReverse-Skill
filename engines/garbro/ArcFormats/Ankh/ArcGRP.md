# Ankh / ArcGRP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GRP/ICE` / `GameRes.Formats.Ankh.GrpOpener` | `grp`, `bin`, `dat`, `vc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GrpOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0);` |
| `GrpOpener.TryOpen` | `next_offset = file.View.ReadUInt32 (index_offset);` |
| `GrpOpener.DetectFileTypes` | `if (header.AsciiEqual ("TPW"))` |
| `GrpOpener.DetectFileTypes` | `entry.UnpackedSize = file.View.ReadUInt32 (start_offset);` |
| `GrpOpener.DetectFileTypes` | `if (file.View.AsciiEqual (start_offset, "BM"))` |
| `GrpOpener.DetectFileTypes` | `else if (header.AsciiEqual (4, "HDJ\0"))` |
| `GrpOpener.DetectFileTypes` | `if (header.AsciiEqual (12, "BM"))` |
| `GrpOpener.DetectFileTypes` | `else if (header.AsciiEqual (12, "MThd"))` |
| `GrpOpener.DetectFileTypes` | `entry.UnpackedSize = header.ToUInt32 (0);` |
| `GrpOpener.DetectFileTypes` | `else if (header.AsciiEqual (0, "zfd "))` |
| `GrpOpener.DetectFileTypes` | `entry.UnpackedSize = header.ToUInt32 (4);` |
| `GrpOpener.DetectFileTypes` | `else if (header.AsciiEqual (4, "OggS"))` |
| `GrpOpener.DetectFileTypes` | `(header.AsciiEqual (8, "RIFF") \|\|` |
| `GrpOpener.DetectFileTypes` | `((header[4] & 0xF) == 0xF && header.AsciiEqual (5, "RIFF"))))` |
| `GrpOpener.DetectFileTypes` | `uint signature = header.ToUInt32 (0);` |
| `GrpOpener.IsAudioEntry` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `GrpOpener.IsAudioEntry` | `int extra = file.View.ReadUInt16 (entry.Offset+0x10);` |
| `GrpOpener.IsAudioEntry` | `uint size = file.View.ReadUInt32 (entry.Offset+0x12);` |
| `GrpOpener.OpenEntry` | `if (arc.File.View.AsciiEqual (entry.Offset, "TPW"))` |
| `GrpOpener.OpenEntry` | `if (arc.File.View.AsciiEqual (entry.Offset+4, "HDJ\0"))` |
| `GrpOpener.OpenEntry` | `if (arc.File.View.AsciiEqual (entry.Offset, "zfd "))` |
| `GrpOpener.OpenEntry` | `byte type = arc.File.View.ReadByte (entry.Offset+4);` |
| `GrpOpener.OpenEntry` | `&& arc.File.View.AsciiEqual (entry.Offset+8, "RIFF"))` |
| `GrpOpener.OpenEntry` | `&& arc.File.View.AsciiEqual (entry.Offset+5, "RIFF"))` |
| `GrpOpener.OpenAudio` | `int unpacked_size = arc.File.View.ReadInt32 (entry.Offset);` |
| `GrpOpener.OpenAudio` | `byte pack_type = arc.File.View.ReadByte (entry.Offset+5);` |
| `GrpOpener.OpenAudio` | `byte channels = arc.File.View.ReadByte (entry.Offset+6);` |
| `GrpOpener.OpenAudio` | `byte header_size = arc.File.View.ReadByte (entry.Offset+7);` |
| `GrpOpener.UnpackTpw` | `offsets[0] = input.ReadUInt16();` |
| `GrpOpener.UnpackTpw` | `byte ctl = input.ReadUInt8();` |
| `GrpOpener.UnpackTpw` | `count = input.ReadUInt16();` |
| `GrpOpener.UnpackTpw` | `byte v = input.ReadUInt8();` |
| `GrpOpener.UnpackTpw` | `int offset = input.ReadUInt8();` |
| `GrpUnpacker.UnpackHDJVariant` | `next_word = m_input.ReadUInt32();` |
| `GrpUnpacker.UnpackHDJVariant` | `next_byte = m_input.ReadUInt32();` |
| `GrpUnpacker.GetBits` | `m_bits = m_input.ReadUInt32();` |
| `GrpUnpacker.GetBits` | `uint next_bits = m_input.ReadUInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum GrpVariant { Default, BoD }
```

### GameRes.Formats.Ankh.GrpOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal static ResourceInstance<AudioFormat> Mp3Format = new ResourceInstance<AudioFormat> ("MP3") ;
```

#### GrpOpener

```csharp
public GrpOpener () {
    Extensions = new string[] { "grp", "bin", "dat", "vc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint first_offset = file.View.ReadUInt32 (0);
    if (first_offset < 8 || first_offset >= file.MaxOffset || 0 != (first_offset & 3))
        return null;
    int count = (int)(first_offset - 4) / 4;
    if (!IsSaneCount (count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_offset = 0;
    uint next_offset = first_offset;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count && next_offset < file.MaxOffset; ++i)
    {
        var entry = new PackedEntry { Offset = next_offset };
        index_offset += 4;
        next_offset = file.View.ReadUInt32 (index_offset);
        if (next_offset < entry.Offset)
            return null;
        entry.Size = (uint)(next_offset - entry.Offset);
        entry.UnpackedSize = entry.Size;
        if (entry.Size != 0)
        {
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.Name = string.Format ("{0}#{1:D4}", base_name, i);
            dir.Add (entry);
        }
    }
    if (0 == dir.Count)
        return null;
    DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

#### DetectFileTypes

```csharp
internal void DetectFileTypes (ArcView file, List<Entry> dir) {
    var header = new byte[16];
    foreach (PackedEntry entry in dir)
    {
        if (entry.Size <= 8)
            continue;
        file.View.Read (entry.Offset, header, 0, 16);
        if (header.AsciiEqual ("TPW"))
        {
            entry.IsPacked =header[3] != 0;
            long start_offset = entry.Offset+4;
            if (entry.IsPacked)
            {
                entry.UnpackedSize = file.View.ReadUInt32 (start_offset);
                start_offset = entry.Offset+11;
            }
            else
            {
                entry.Offset = start_offset;
                entry.Size -= 4;
            }
            if (file.View.AsciiEqual (start_offset, "BM"))
                entry.ChangeType (ImageFormat.Bmp);
        }
        else if (header.AsciiEqual (4, "HDJ\0"))
        {
            if (header.AsciiEqual (12, "BM"))
                entry.ChangeType (ImageFormat.Bmp);
            else if (header.AsciiEqual (12, "MThd"))
                entry.Name = Path.ChangeExtension (entry.Name, "mid");

            entry.UnpackedSize = header.ToUInt32 (0);
            entry.IsPacked = true;
        }
        else if (header.AsciiEqual (0, "zfd "))
        {
            entry.ChangeType (ImageFormat.Tga);
            entry.UnpackedSize = header.ToUInt32 (4);
            entry.IsPacked = true;
        }
        else if (header.AsciiEqual (4, "OggS"))
        {
            entry.ChangeType (OggAudio.Instance);
            entry.Offset += 4;
            entry.Size   -= 4;
        }
        else if (entry.Size > 12 &&
                 (header.AsciiEqual (8, "RIFF") ||
                  ((header[4] & 0xF) == 0xF && header.AsciiEqual (5, "RIFF"))))
        {
            entry.ChangeType (AudioFormat.Wav);
            entry.UnpackedSize = header.ToUInt32 (0);
            entry.IsPacked = true;
        }
        else
        {
            uint signature = header.ToUInt32 (0);
            var res = AutoEntry.DetectFileType (signature);
            if (res != null)
            {
                entry.ChangeType (res);
            }
            else if ((signature & 0xFFFF) == 0xFBFF)
            {
                entry.ChangeType (Mp3Format.Value);
            }
            else if (entry.Size > 0x16 && IsAudioEntry (file, entry))
            {
                entry.Type = "audio";
            }
        }
    }
}
```

#### IsAudioEntry

```csharp
bool IsAudioEntry (ArcView file, Entry entry) {
    uint signature = file.View.ReadUInt32 (entry.Offset);
    if (signature != 0x010001 && signature != 0x020001)
        return false;
    int extra = file.View.ReadUInt16 (entry.Offset+0x10);
    if (extra != 0)
        return false;
    uint size = file.View.ReadUInt32 (entry.Offset+0x12);
    return 0x16 + size == entry.Size;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (pent != null && pent.IsPacked && pent.Size > 8)
    {
        try
        {
            if (arc.File.View.AsciiEqual (entry.Offset, "TPW"))
                return OpenTpw (arc, pent);
            if (arc.File.View.AsciiEqual (entry.Offset+4, "HDJ\0"))
                return OpenImage (arc, pent);
            if (arc.File.View.AsciiEqual (entry.Offset, "zfd "))
                return OpenZfd (arc, pent);
            if (entry.Size > 12)
            {
                byte type = arc.File.View.ReadByte (entry.Offset+4);
                if ('W' == type
                    && arc.File.View.AsciiEqual (entry.Offset+8, "RIFF"))
                    return OpenAudio (arc, entry);
                if ((type & 0xF) == 0xF
                    && arc.File.View.AsciiEqual (entry.Offset+5, "RIFF"))
                {
                    var input = arc.File.CreateStream (entry.Offset+4, entry.Size-4);
                    return new LzssStream (input);
                }
            }
        }
        catch (Exception X)
        {
            System.Diagnostics.Trace.WriteLine (X.Message, "[GRP]");
        }
    }
    return base.OpenEntry (arc, entry);
}
```

#### OpenImage

```csharp
Stream OpenImage (ArcFile arc, PackedEntry entry) {
    using (var packed = arc.File.CreateStream (entry.Offset+8, entry.Size-8))
    using (var reader = new GrpUnpacker (packed))
    {
        var unpacked = new byte[entry.UnpackedSize];
        reader.UnpackHDJ (unpacked, 0);
        return new BinMemoryStream (unpacked, entry.Name);
    }
}
```

#### OpenAudio

```csharp
Stream OpenAudio (ArcFile arc, Entry entry) {
    int unpacked_size = arc.File.View.ReadInt32 (entry.Offset);
    byte pack_type = arc.File.View.ReadByte (entry.Offset+5);
    byte channels = arc.File.View.ReadByte (entry.Offset+6);
    byte header_size = arc.File.View.ReadByte (entry.Offset+7);
    if (unpacked_size <= 0 || header_size > unpacked_size
        || !('A' == pack_type || 'S' == pack_type))
        return base.OpenEntry (arc, entry);
    var unpacked = new byte[unpacked_size];
    arc.File.View.Read (entry.Offset+8, unpacked, 0, header_size);
    uint packed_size = entry.Size - 8 - header_size;
    using (var packed = arc.File.CreateStream (entry.Offset+8+header_size, packed_size))
    using (var reader = new GrpUnpacker (packed))
    {
        if ('A' == pack_type)
            reader.UnpackA (unpacked, header_size, channels);
        else
            reader.UnpackS (unpacked, header_size, channels);
        return new BinMemoryStream (unpacked, entry.Name);
    }
}
```

#### OpenTpw

```csharp
Stream OpenTpw (ArcFile arc, PackedEntry entry) {
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var output = new byte[entry.UnpackedSize];
        UnpackTpw (input, output);
        return new BinMemoryStream (output, entry.Name);
    }
}
```

#### OpenZfd

```csharp
Stream OpenZfd (ArcFile arc, PackedEntry entry) {
    var input = arc.File.CreateStream (entry.Offset+8, entry.Size-8);
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

#### UnpackTpw

```csharp
internal static void UnpackTpw (IBinaryStream input, byte[] output) {
    input.Position = 8;
    var offsets = new int[4];
    offsets[0] = input.ReadUInt16();
    offsets[1] = offsets[0] * 2;
    offsets[2] = offsets[0] * 3;
    offsets[3] = offsets[0] * 4;
    int dst = 0;
    while (dst < output.Length)
    {
        byte ctl = input.ReadUInt8();
        if (0 == ctl)
            break;
        int remaining = output.Length - dst;
        int count;
        if (ctl < 0x40)
        {
            count = Math.Min (ctl, remaining);
            input.Read (output, dst, count);
            dst += count;
        }
        else if (ctl <= 0x6F)
        {
            if (0x6F == ctl)
                count = input.ReadUInt16();
            else
                count = (byte)(ctl - 0x3D);
            count = Math.Min (count, remaining);
            byte v = input.ReadUInt8();
            while (count --> 0)
                output[dst++] = v;
        }
        else if (ctl <= 0x9F)
        {
            if (ctl == 0x9F)
                count = input.ReadUInt16();
            else
                count = (byte)(ctl - 0x6E);
            dst += input.Read (output, dst, Math.Min (2, remaining));
            --count;
            if (count > 0 && remaining > 2)
            {
                count = Math.Min (count * 2, remaining - 2);
                Binary.CopyOverlapped (output, dst-2, dst, count);
                dst += count;
            }
        }
        else if (ctl <= 0xBF)
        {
            if (ctl == 0xBF)
                count = input.ReadUInt16();
            else
                count = (byte)(ctl - 0x9E);
            dst += input.Read (output, dst, Math.Min (3, remaining));
            --count;
            if (count > 0 && remaining > 3)
            {
                count = Math.Min (count * 3, remaining - 3);
                Binary.CopyOverlapped (output, dst-3, dst, count);
                dst += count;
            }
        }
        else
        {
            count = Math.Min ((ctl & 0x3F) + 3, remaining);
            int offset = input.ReadUInt8();
            offset = (offset & 0x3F) - offsets[offset >> 6];
            Binary.CopyOverlapped (output, dst+offset, dst, count);
            dst += count;
        }
    }
}
```

### GameRes.Formats.Ankh.GrpUnpacker

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream       m_input ;

uint                m_bits ;

int                 m_cached_bits ;

enum GrpVariant { Default, BoD }

static GrpVariant LastUsedMethod = GrpVariant.Default ;

bool _disposed = false ;
```

#### GrpUnpacker

```csharp
public GrpUnpacker (IBinaryStream input) {
    m_input = input;
}
```

#### GetOppositeVariant

```csharp
static GrpVariant GetOppositeVariant () {
    return GrpVariant.Default == LastUsedMethod ? GrpVariant.BoD : GrpVariant.Default;
}
```

#### UnpackHDJ

```csharp
public void UnpackHDJ (byte[] output, int dst) {
    try
    {
        if (UnpackHDJVariant (output, dst, LastUsedMethod))
            return;
    }
    catch {  }
    var method = GetOppositeVariant();
    m_input.Position = 0;
    if (!UnpackHDJVariant (output, dst, method))
        throw new InvalidFormatException();
    LastUsedMethod = method;
}
```

#### UnpackHDJVariant

```csharp
private bool UnpackHDJVariant (byte[] output, int dst, GrpVariant method) {
    ResetBits();
    int word_count = 0;
    int byte_count = 0;
    uint next_byte = 0;
    uint next_word = 0;
    while (dst < output.Length)
    {
        if (GetNextBit() != 0)
        {
            int count = 0;
            bool long_count = false;
            int offset;
            if (GetNextBit() != 0)
            {
                if (0 == word_count)
                {
                    next_word = m_input.ReadUInt32();
                    word_count = 2;
                }
                count = (int)((next_word >> 13) & 7) + 3;
                offset = (int)(next_word | 0xFFFFE000);
                next_word >>= 16;
                --word_count;
                long_count = 10 == count;
            }
            else
            {
                if (method == GrpVariant.Default)
                    count = GetBits (2);
                if (0 == byte_count)
                {
                    next_byte = m_input.ReadUInt32();
                    byte_count = 4;
                }
                if (method != GrpVariant.Default)
                    count = GetBits (2);
                count += 2;
                long_count = 5 == count;
                offset = (int)(next_byte | 0xFFFFFF00);
                next_byte >>= 8;
                --byte_count;
            }
            if (long_count)
            {
                int n = 0;
                while (GetNextBit() != 0)
                    ++n;

                if (n != 0)
                    count += GetBits (n) + 1;
            }
            int src = dst + offset;
            if (src < 0 || src >= dst || dst + count > output.Length)
                return false;
            Binary.CopyOverlapped (output, src, dst, count);
            dst += count;
        }
        else
        {
            if (0 == byte_count)
            {
                next_byte = m_input.ReadUInt32();
                byte_count = 4;
            }
            output[dst++] = (byte)next_byte;
            next_byte >>= 8;
            --byte_count;
        }
    }
    return true;
}
```

#### UnpackS

```csharp
public void UnpackS (byte[] output, int dst, int channels) {
    try
    {
        if (UnpackSVariant (output, dst, channels, LastUsedMethod))
            return;
    }
    catch {  }
    var method = GetOppositeVariant();
    m_input.Position = 0;
    if (UnpackSVariant (output, dst, channels, method))
        LastUsedMethod = method;
}
```

#### UnpackSVariant

```csharp
bool UnpackSVariant (byte[] output, int dst, int channels, GrpVariant method) {
    if (GrpVariant.Default == method)
        UnpackSv2 (output, dst, channels);
    else
        UnpackSv1 (output, dst, channels);
    return m_input.PeekByte() == -1;
}
```

#### UnpackSv1

```csharp
void UnpackSv1 (byte[] output, int dst, int channels) {
    ResetBits();
    short last_word = 0;
    while (dst < output.Length)
    {
        int word;
        if (GetNextBit() != 0)
        {
            if (GetNextBit() != 0)
                word = GetBits (10) << 6;
            else
                word = 0;
        }
        else
        {
            int adjust = GetBits (5) << 6;
            if (0 != (adjust & 0x400))
                adjust = -(adjust & 0x3FF);
            word = last_word + adjust;
        }
        last_word = (short)word;
        LittleEndian.Pack (last_word, output, dst);
        dst += 2;
    }
}
```

#### UnpackSv2

```csharp
void UnpackSv2 (byte[] output, int dst, int channels) {
    if (channels != 1)
        m_input.Seek ((channels-1) * 4, SeekOrigin.Current);
    int step = channels * 2;
    for (int i = 0; i < channels; ++i)
    {
        ResetBits();
        int pos = dst;
        short last_word = 0;
        while (pos < output.Length)
        {
            int word;
            if (GetNextBit() != 0)
            {
                if (GetNextBit() != 0)
                {
                    word = GetBits (10) << 6;
                }
                else
                {
                    int repeat;
                    if (GetNextBit() != 0)
                    {
                        int bit_length = 0;
                        do
                        {
                            ++bit_length;
                        }
                        while (GetNextBit() != 0);
                        repeat = GetBits (bit_length) + 4;
                    }
                    else
                    {
                        repeat = GetBits (2);
                    }
                    word = 0;
                    while (repeat --> 0)
                    {
                        output[pos]   = 0;
                        output[pos+1] = 0;
                        pos += step;
                    }
                }
            }
            else
            {
                int adjust = (short)(GetBits (5) << 11) >> 5;
                word = last_word + adjust;
            }
            LittleEndian.Pack ((short)word, output, pos);
            last_word = (short)word;
            pos += step;
        }
        dst += 2;
    }
}
```

#### UnpackA

```csharp
public void UnpackA (byte[] output, int dst, int channels) {
    if (channels != 1)
        m_input.Seek ((channels-1) * 4, SeekOrigin.Current);
    int step = 2 * channels;
    for (int i = 0; i < channels; ++i)
    {
        int pos = dst;
        ResetBits();
        while (pos < output.Length)
        {
            int word = GetBits (10) << 6;;
            LittleEndian.Pack ((short)word, output, pos);
            pos += step;
        }
        dst += 2;
    }
}
```

#### ResetBits

```csharp
void ResetBits () {
    m_cached_bits = 0;
}
```

#### GetNextBit

```csharp
int GetNextBit () {
    return GetBits (1);
}
```

#### GetBits

```csharp
int GetBits (int count) {
    if (0 == m_cached_bits)
    {
        m_bits = m_input.ReadUInt32();
        m_cached_bits = 32;
    }
    uint val;
    if (m_cached_bits < count)
    {
        uint next_bits = m_input.ReadUInt32();
        val = (m_bits | (next_bits >> m_cached_bits)) >> (32 - count);
        m_bits = next_bits << (count - m_cached_bits);
        m_cached_bits = 32 - (count - m_cached_bits);
    }
    else
    {
        val = m_bits >> (32 - count);
        m_bits <<= count;
        m_cached_bits -= count;
    }
    return (int)val;
}
```

## 配套算法与外部条件

- [ArcFormats/AudioOGG.cs](../AudioOGG.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Ankh/ArcGRP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
