# Maika / ArcMK2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/MK2` / `GameRes.Formats.Maika.Mk2Opener` | `dat` | `4d4b322e`, `424c322e`, `534c312e`, `4c53322e`, `4152322e`, `4d50322e` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Mk2Opener.TryOpen` | `if (!file.View.AsciiEqual (4, "0\0"))` |
| `Mk2Opener.TryOpen` | `int count = file.View.ReadInt32 (0x12);` |
| `Mk2Opener.TryOpen` | `uint base_offset  = file.View.ReadUInt16 (8);` |
| `Mk2Opener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0xE);` |
| `Mk2Opener.TryOpen` | `uint index_size   = file.View.ReadUInt32 (0xA);` |
| `Mk2Opener.TryOpen` | `uint entry_offset = index_offset + file.View.ReadUInt32 (current_offset);` |
| `Mk2Opener.TryOpen` | `int n = file.View.ReadUInt16 (current_offset+4);` |
| `Mk2Opener.TryOpen` | `uint offset = file.View.ReadUInt32 (entry_offset) + base_offset;` |
| `Mk2Opener.TryOpen` | `uint size   = file.View.ReadUInt32 (entry_offset+4);` |
| `Mk2Opener.TryOpen` | `uint name_length = file.View.ReadByte (entry_offset+8);` |
| `Mk2Opener.TryOpen` | `var name = file.View.ReadString (entry_offset+9, name_length);` |
| `Mk2Opener.TryOpen` | `else if (-1 == file.View.ReadInt32 (entry_offset))` |
| `Mk2Opener.GetArchive` | `string arc_id = file.View.ReadString (0, 5);` |
| `Mk2Opener.OpenEntry` | `ushort signature = arc.File.View.ReadUInt16 (entry.Offset);` |
| `Mk2Opener.OpenEntry` | `uint packed_size = arc.File.View.ReadUInt32 (entry.Offset+2);` |
| `Mk2Opener.OpenEntry` | `var prefix = arc.File.View.ReadBytes (entry.Offset+10, scheme.ScrambledSize);` |
| `Mk2Opener.OpenEntry` | `if (Binary.AsciiEqual (header, "BPR02"))` |
| `Mk2Opener.OpenEntry` | `if (Binary.AsciiEqual (header, "BPR01"))` |
| `BprDecompressor.Unpack` | `int ctl = m_input.ReadByte();` |
| `BprDecompressor.Unpack` | `int count = m_input.ReadInt32();` |
| `BprDecompressor.Unpack` | `byte b = m_input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Maika.ScrambleScheme

#### 状态与常量

```csharp
public uint                 ScrambledSize ;

public Tuple<byte, byte>[]  ScrambleMap ;
```

### GameRes.Formats.Maika.MkArchive

继承/接口：`ArcFile`。

#### MkArchive

```csharp
public MkArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ScrambleScheme scheme)
    : base (arc, impl, dir) {
    Scheme = scheme;
}
```

### GameRes.Formats.Maika.Mk2Opener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ScrambleScheme DefaultScheme = new ScrambleScheme {
    ScrambledSize = 14,
    ScrambleMap = new Tuple<byte,byte>[] {
        new Tuple<byte, byte> (7, 11),
        new Tuple<byte, byte> (9, 12)
    }
}

static readonly ScrambleScheme ArScheme = new ScrambleScheme {
    ScrambledSize = 15,
    ScrambleMap = new Tuple<byte,byte>[] {
        new Tuple<byte, byte> (7, 13),
        new Tuple<byte, byte> (9, 14)
    }
}
```

#### Mk2Opener

```csharp
public Mk2Opener () {

    Signatures = new uint[] {
        0x2E324B4D, 0x2E324C42, 0x2E314C53, 0x2E32534C, 0x2E325241, 0x2E32504D
    };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "0\0"))
        return null;
    int count = file.View.ReadInt32 (0x12);
    if (!IsSaneCount (count))
        return null;

    uint base_offset  = file.View.ReadUInt16 (8);
    uint index_offset = file.View.ReadUInt32 (0xE);
    if (index_offset >= file.MaxOffset)
        return null;
    uint index_size   = file.View.ReadUInt32 (0xA);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;

    uint current_offset = index_offset;
    var dir = new List<Entry> (count);
    for (int i = 0; i < 512; ++i)
    {
        uint entry_offset = index_offset + file.View.ReadUInt32 (current_offset);
        int n = file.View.ReadUInt16 (current_offset+4);
        if (n > 0)
        {
            for (int j = 0; j < n; ++j)
            {
                uint offset = file.View.ReadUInt32 (entry_offset) + base_offset;
                uint size   = file.View.ReadUInt32 (entry_offset+4);
                uint name_length = file.View.ReadByte (entry_offset+8);
                if (0 == name_length)
                    return null;
                var name = file.View.ReadString (entry_offset+9, name_length);
                entry_offset += 9 + name_length;

                var entry = FormatCatalog.Instance.Create<Entry> (name);
                entry.Offset = offset;
                entry.Size   = size;
                if (!entry.CheckPlacement (index_offset))
                    return null;
                dir.Add (entry);
            }
        }
        else if (-1 == file.View.ReadInt32 (entry_offset))
            break;
        current_offset += 6;
    }
    return GetArchive (file, dir);
}
```

#### GetArchive

```csharp
internal ArcFile GetArchive (ArcView file, List<Entry> dir) {
    if (0 == dir.Count)
        return null;
    string arc_id = file.View.ReadString (0, 5);
    ScrambleScheme scheme;
    if (!KnownSchemes.TryGetValue (arc_id, out scheme))
        scheme = DefaultScheme;
    return new MkArchive (file, this, dir, scheme);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    ushort signature = arc.File.View.ReadUInt16 (entry.Offset);

    if (0x3146 != signature && 0x3143 != signature && 0x3144 != signature && 0x3145 != signature)
        return base.OpenEntry (arc, entry);
    var mkarc = arc as MkArchive;
    ScrambleScheme scheme = mkarc != null ? mkarc.Scheme : DefaultScheme;

    uint packed_size = arc.File.View.ReadUInt32 (entry.Offset+2);
    if (packed_size < scheme.ScrambledSize || packed_size > entry.Size-10)
        return base.OpenEntry (arc, entry);

    Stream input;

    if (0x3145 == signature && scheme.ScrambledSize > 0)
    {
        var prefix = arc.File.View.ReadBytes (entry.Offset+10, scheme.ScrambledSize);
        foreach (var pair in scheme.ScrambleMap)
        {
            byte t = prefix[pair.Item1];
            prefix[pair.Item1] = prefix[pair.Item2];
            prefix[pair.Item2] = t;
        }
        input = arc.File.CreateStream (entry.Offset+10+scheme.ScrambledSize, packed_size-scheme.ScrambledSize);
        input = new PrefixStream (prefix, input);
    }
    else
    {
        input = arc.File.CreateStream (entry.Offset+10, packed_size);
    }
    input = new LzssStream (input);

    var header = new byte[5];
    input.Read (header, 0, 5);
    if (Binary.AsciiEqual (header, "BPR02"))
        return new PackedStream<Bpr02Decompressor> (input);
    if (Binary.AsciiEqual (header, "BPR01"))
        return new PackedStream<Bpr01Decompressor> (input);
    return new PrefixStream (header, input);
}
```

### GameRes.Formats.Maika.BprDecompressor

继承/接口：`Decompressor`。

#### 状态与常量

```csharp
readonly byte   m_rle_code ;

IBinaryStream   m_input ;

bool m_disposed = false ;
```

#### BprDecompressor

```csharp
protected BprDecompressor (byte rle_code) {
    m_rle_code = rle_code;
}
```

#### Initialize

```csharp
public override void Initialize (Stream input) {
    m_input = new BinaryStream (input, "");
}
```

#### Unpack

```csharp
protected override IEnumerator<int> Unpack () {
    for (;;)
    {
        int ctl = m_input.ReadByte();
        if (-1 == ctl || 0xFF == ctl)
            yield break;
        int count = m_input.ReadInt32();
        if (m_rle_code == ctl)
        {
            byte b = m_input.ReadUInt8();
            while (count --> 0)
            {
                m_buffer[m_pos++] = b;
                if (0 == --m_length)
                    yield return m_pos;
            }
        }
        else
        {
            while (count > 0)
            {
                int chunk = Math.Min (count, m_length);
                int read = m_input.Read (m_buffer, m_pos, chunk);
                count -= chunk;
                m_pos += chunk;
                m_length -= chunk;
                if (0 == m_length)
                    yield return m_pos;
            }
        }
    }
}
```

### GameRes.Formats.Maika.Bpr02Decompressor

继承/接口：`BprDecompressor`。

### GameRes.Formats.Maika.Bpr01Decompressor

继承/接口：`BprDecompressor`。

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Maika/ArcMK2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
