# AZSys / ArcAZSys：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/AZ` / `GameRes.Formats.AZSys.ArcOpener` | `arc` | `4152431a` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int ext_count = file.View.ReadInt32 (4);` |
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `ArcOpener.TryOpen` | `uint index_length = file.View.ReadUInt32 (12);` |
| `ArcOpener.TryOpen` | `var packed_index = file.View.ReadBytes (0x30, index_length);` |
| `ArcOpener.TryOpen` | `uint crc = LittleEndian.ToUInt32 (packed_index, 0);` |
| `ArcOpener.TryOpen` | `entry.Offset = base_offset + LittleEndian.ToUInt32 (index, index_offset);` |
| `ArcOpener.TryOpen` | `entry.Size = LittleEndian.ToUInt32 (index, index_offset + 4);` |
| `ArcOpener.OpenEntry` | `\|\| !arc.File.View.AsciiEqual (entry.Offset, "ASB\x1a"))` |
| `ArcOpener.OpenEntry` | `uint packed   = arc.File.View.ReadUInt32 (entry.Offset+4);` |
| `ArcOpener.OpenEntry` | `uint unpacked = arc.File.View.ReadUInt32 (entry.Offset+8);` |
| `ArcOpener.OpenEntry` | `uint first = arc.File.View.ReadUInt16 (entry.Offset+16);` |
| `ArcOpener.OpenEntry` | `var input = arc.File.View.ReadBytes (entry.Offset+12, packed);` |
| `ArcOpener.OpenEntry` | `uint checksum = LittleEndian.ToUInt32 (input, 0);` |
| `IndexReader.IndexReader` | `m_control_len = LittleEndian.ToInt32 (packed, 4);` |
| `IndexReader.IndexReader` | `m_compr1_len = LittleEndian.ToInt32 (packed, 8);` |
| `IndexReader.IndexReader` | `m_compr2_len = LittleEndian.ToInt32 (packed, 12);` |
| `IndexReader.IndexReader` | `m_output_len = LittleEndian.ToInt32 (packed, 0x10);` |
| `IndexReader.Unpack` | `int offset = LittleEndian.ToUInt16 (m_input, compr1);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AZSys.AsbOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public uint AsbKey ;
```

### GameRes.Formats.AZSys.AsbArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly uint Key ;
```

#### AsbArchive

```csharp
public AsbArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, uint key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.AZSys.ArcOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static AsbScheme DefaultScheme = new AsbScheme { KnownKeys = new Dictionary<string, uint>() }
```

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int ext_count = file.View.ReadInt32 (4);
    int count = file.View.ReadInt32 (8);
    uint index_length = file.View.ReadUInt32 (12);
    if (ext_count < 1 || ext_count > 8 || count <= 0 || count > 0xfffff
        || index_length <= 0x14 || index_length >= file.MaxOffset)
        return null;
    var packed_index = file.View.ReadBytes (0x30, index_length);
    if (packed_index.Length != index_length)
        return null;
    uint base_offset = 0x30 + index_length;
    uint crc = LittleEndian.ToUInt32 (packed_index, 0);
    if (crc != Crc32.Compute (packed_index, 0x14, packed_index.Length-0x14))
        throw new InvalidFormatException ("CRC32 mismatch");
    var reader = new IndexReader (packed_index, count);
    var index = reader.Unpack();
    int index_offset = 0;
    bool contains_scripts = false;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, index_offset + 0x10, 0x30);
        if (name.Length > 0)
        {
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = base_offset + LittleEndian.ToUInt32 (index, index_offset);
            entry.Size = LittleEndian.ToUInt32 (index, index_offset + 4);
            if (entry.CheckPlacement (file.MaxOffset))
            {
                dir.Add (entry);
                contains_scripts = contains_scripts || name.HasExtension (".asb");
            }
        }
        index_offset += 0x40;
    }
    if (0 == dir.Count)
        return null;
    if (!contains_scripts || 0 == KnownKeys.Count)
        return new ArcFile (file, this, dir);
    var options = Query<AsbOptions> (arcStrings.ArcEncryptedNotice);
    if (0 == options.AsbKey)
        return new ArcFile (file, this, dir);
    return new AsbArchive (file, this, dir, options.AsbKey);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var azarc = arc as AsbArchive;
    if (null == azarc || entry.Size < 20
        || !arc.File.View.AsciiEqual (entry.Offset, "ASB\x1a"))
        return arc.File.CreateStream (entry.Offset, entry.Size);
    uint packed   = arc.File.View.ReadUInt32 (entry.Offset+4);
    uint unpacked = arc.File.View.ReadUInt32 (entry.Offset+8);
    if (12 + packed != entry.Size)
        return arc.File.CreateStream (entry.Offset, entry.Size);

    uint key = azarc.Key ^ unpacked;
    key ^= ((key << 12) | key) << 11;

    uint first = arc.File.View.ReadUInt16 (entry.Offset+16);
    first = (first - key) & 0xffff;
    if (first != 0xda78)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var input = arc.File.View.ReadBytes (entry.Offset+12, packed);
    unsafe
    {
        fixed (byte* raw = input)
        {
            uint* encoded = (uint*)raw;
            for (int i = 0; i < input.Length/4; ++i)
                encoded[i] -= key;
        }
    }

    uint checksum = LittleEndian.ToUInt32 (input, 0);
    if (checksum != Crc32.Compute (input, 4, input.Length-4))
        return arc.File.CreateStream (entry.Offset, entry.Size);
    return new ZLibStream (new MemoryStream (input, 4, input.Length-4), CompressionMode.Decompress);
}
```

#### GetAsbKey

```csharp
uint GetAsbKey (string scheme) {
    uint key;
    if (KnownKeys.TryGetValue (scheme, out key))
        return key;
    return 0;
}
```

### GameRes.Formats.AZSys.ArcOpener.IndexReader

#### 状态与常量

```csharp
byte[]  m_input ;

byte[]  m_output ;

int     m_control_len ;

int     m_compr1_len ;

int     m_compr2_len ;

int     m_output_len ;

public byte[] Index { get { return m_output; } }
```

#### IndexReader

```csharp
public IndexReader (byte[] packed, int count) {
    m_input = packed;
    m_output = new byte[count*0x40];
    m_control_len = LittleEndian.ToInt32 (packed, 4);
    m_compr1_len = LittleEndian.ToInt32 (packed, 8);
    m_compr2_len = LittleEndian.ToInt32 (packed, 12);
    m_output_len = LittleEndian.ToInt32 (packed, 0x10);
}
```

#### Unpack

```csharp
public byte[] Unpack () {
    int control = 0x14;
    int compr1 = control + m_control_len;
    int compr2 = compr1 + m_compr1_len;
    int dst = 0;
    byte mask = 0x80;
    int copy_count;
    while (dst < m_output.Length)
    {
        if (0 != (m_input[control] & mask))
        {
            int offset = LittleEndian.ToUInt16 (m_input, compr1);
            compr1 += 2;
            copy_count = (offset >> 13) + 3;
            offset &= 0x1fff;
            offset++;
            Binary.CopyOverlapped (m_output, dst-offset, dst, copy_count);
            dst += copy_count;
        }
        else
        {
            copy_count = m_input[compr2++] + 1;
            Buffer.BlockCopy (m_input, compr2, m_output, dst, copy_count);
            compr2 += copy_count;
            dst += copy_count;
        }
        mask >>= 1;
        if (0 == mask)
        {
            ++control;
            mask = 0x80;
        }
    }
    return m_output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/AZSys/ArcAZSys.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
