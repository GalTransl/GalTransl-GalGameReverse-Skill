# SakanaGL / ArcSX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SXSTORAGE` / `GameRes.Formats.Sakana.SxOpener` | `sxstorage` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SxOpener.TryOpen` | `if (!sx.View.AsciiEqual (0, "SSXXDEFL"))` |
| `SxOpener.TryOpen` | `int key = Binary.BigEndian (sx.View.ReadInt32 (8));` |
| `SxOpener.TryOpen` | `var index_packed = sx.View.ReadBytes (0x10, (uint)length);` |
| `SxOpener.OpenEntry` | `var input = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `SxOpener.UnpackZstd` | `int unpacked_size = BigEndian.ToInt32 (data, 0);` |
| `SxIndexDeserializer.Deserialize` | `int count = Binary.BigEndian (m_index.ReadInt32());` |
| `SxIndexDeserializer.Deserialize` | `int length = m_index.ReadUInt8();` |
| `SxIndexDeserializer.Deserialize` | `m_name_list[i] = m_index.ReadCString (length, Encoding.UTF8);` |
| `SxIndexDeserializer.Deserialize` | `count = Binary.BigEndian (m_index.ReadInt32());` |
| `SxIndexDeserializer.Deserialize` | `ushort arc   = Binary.BigEndian (m_index.ReadUInt16());` |
| `SxIndexDeserializer.Deserialize` | `ushort flags = Binary.BigEndian (m_index.ReadUInt16());` |
| `SxIndexDeserializer.Deserialize` | `uint offset  = Binary.BigEndian (m_index.ReadUInt32());` |
| `SxIndexDeserializer.Deserialize` | `uint size    = Binary.BigEndian (m_index.ReadUInt32());` |
| `SxIndexDeserializer.Deserialize` | `int arc_count = Binary.BigEndian (m_index.ReadUInt16());` |
| `SxIndexDeserializer.Deserialize` | `m_index.ReadUInt32();` |
| `SxIndexDeserializer.Deserialize` | `long arc_size = (long)Binary.BigEndian (m_index.ReadUInt32()) << 4;` |
| `SxIndexDeserializer.Deserialize` | `m_index.ReadUInt64();` |
| `SxIndexDeserializer.Deserialize` | `count = Binary.BigEndian (m_index.ReadUInt16());` |
| `SxIndexDeserializer.DeserializeTree` | `int count = Binary.BigEndian (m_index.ReadUInt16());` |
| `SxIndexDeserializer.DeserializeTree` | `int name_index = Binary.BigEndian (m_index.ReadInt32());` |
| `SxIndexDeserializer.DeserializeTree` | `int file_index = Binary.BigEndian (m_index.ReadInt32());` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Sakana.SxEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public ushort   Flags ;

public ushort   ArcIndex ;

public bool IsEncrypted { get { return 0 == (Flags & 0x10); } }
```

### GameRes.Formats.Sakana.SxOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const uint DefaultKey = 0x2E76034B ;

static readonly Regex ArchiveNameRe = new Regex (@"^(.*)-([^-]+)$") ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var sx_name = base_name.Substring (0, 4) + "(00).sx";
    sx_name = VFS.ChangeFileName (file.Name, sx_name);
    if (!VFS.FileExists (sx_name))
    {
        var match = ArchiveNameRe.Match (base_name);
        if (!match.Success)
            return null;
        sx_name = VFS.ChangeFileName (file.Name, match.Groups[1] + "(00).sx");
        if (!VFS.FileExists (sx_name))
            return null;
    }
    if (file.Name.Equals (sx_name, StringComparison.OrdinalIgnoreCase))
        return null;
    byte[] index_data;
    using (var sx = VFS.OpenView (sx_name))
    {
        if (sx.MaxOffset <= 0x10)
            return null;
        if (!sx.View.AsciiEqual (0, "SSXXDEFL"))
            return null;
        int key = Binary.BigEndian (sx.View.ReadInt32 (8));
        int length = (int)(sx.MaxOffset - 0x10);
        var index_packed = sx.View.ReadBytes (0x10, (uint)length);

        long lkey = (long)key + length;
        lkey = key ^ (961 * lkey - 124789) ^ DefaultKey;
        uint key_lo = (uint)lkey;
        uint key_hi = (uint)(lkey >> 32) ^ 0x2E6;
        DecryptData (index_packed, key_lo, key_hi);

        index_data = UnpackZstd (index_packed);
    }
    using (var index = new BinMemoryStream (index_data))
    {
        var reader = new SxIndexDeserializer (index, file.MaxOffset);
        var dir = reader.Deserialize();
        if (null == dir || dir.Count == 0)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var sx_entry = entry as SxEntry;
    if (null == sx_entry || (!sx_entry.IsEncrypted && !sx_entry.IsPacked))
        return base.OpenEntry (arc, entry);
    var input = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    if (sx_entry.IsEncrypted)
    {
        uint key_lo = (uint)(entry.Offset >> 4) ^ (entry.Size << 16) ^ DefaultKey;
        uint key_hi = (entry.Size >> 16) ^ 0x2E6;
        DecryptData (input, key_lo, key_hi);
    }
    if (sx_entry.IsPacked)
    {
        input = UnpackZstd (input);
        if (sx_entry.UnpackedSize == 0)
            sx_entry.UnpackedSize = (uint)input.Length;
    }
    return new BinMemoryStream (input, entry.Name);
}
```

#### UnpackZstd

```csharp
internal static byte[] UnpackZstd (byte[] data) {
    int unpacked_size = BigEndian.ToInt32 (data, 0);
    using (var dec = new ZstdSharp.Decompressor())
    {
        var packed = new Span<byte> (data, 4, data.Length - 4);
        return dec.Unwrap (packed, unpacked_size).ToArray();
    }
}
```

#### DecryptData

```csharp
internal static void DecryptData (byte[] data, uint key_lo, uint key_hi) {
    if (data.Length < 4)
        return;
    key_lo ^= 0x159A55E5;
    key_hi ^= 0x075BCD15;
    uint v1 = key_hi ^ (key_hi << 11) ^ ((key_hi ^ (key_hi << 11)) >> 8) ^ 0x549139A;
    uint v2 = v1 ^ key_lo ^ (key_lo << 11) ^ ((key_lo ^ (key_lo << 11) ^ (v1 >> 11)) >> 8);
    uint v3 = v2 ^ (v2 >> 19) ^ 0x8E415C26;
    uint v4 = v3 ^ (v3 >> 19) ^ 0x4D9D5BB8;
    int count = data.Length / 4;
    unsafe
    {
        fixed (byte* data_raw = data)
        {
            uint* data32 = (uint*)&data_raw[0];
            for (int i = 0; i < count; ++i)
            {
                uint t1 = v4 ^ v1 ^ (v1 << 11) ^ ((v1 ^ (v1 << 11) ^ (v4 >> 11)) >> 8);
                uint t2 = v2 ^ (v2 << 11);
                v2 = v4;
                v4 = t1 ^ t2 ^ ((t2 ^ (t1 >> 11)) >> 8);
                data32[i] ^= (t1 >> 4) ^ (v4 << 12);
                v1 = v3;
                v3 = t1;
            }
        }
    }
}
```

### GameRes.Formats.Sakana.SxIndexDeserializer

#### 状态与常量

```csharp
IBinaryStream   m_index ;

long            m_max_offset ;

string[]        m_name_list ;

List<Entry>     m_dir ;
```

#### SxIndexDeserializer

```csharp
public SxIndexDeserializer (IBinaryStream index, long max_offset) {
    m_index = index;
    m_max_offset = max_offset;
}
```

#### Deserialize

```csharp
public List<Entry> Deserialize () {
    m_index.Position = 8;
    int count = Binary.BigEndian (m_index.ReadInt32());
    m_name_list = new string[count];
    for (int i = 0; i < count; ++i)
    {
        int length = m_index.ReadUInt8();
        m_name_list[i] = m_index.ReadCString (length, Encoding.UTF8);
    }

    count = Binary.BigEndian (m_index.ReadInt32());
    m_dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        ushort arc   = Binary.BigEndian (m_index.ReadUInt16());
        ushort flags = Binary.BigEndian (m_index.ReadUInt16());
        uint offset  = Binary.BigEndian (m_index.ReadUInt32());
        uint size    = Binary.BigEndian (m_index.ReadUInt32());
        var entry = new SxEntry {
            Flags  = flags,
            Offset = (long)offset << 4,
            Size   = size,
            IsPacked = 0 != (flags & 0x03),
            ArcIndex = arc,
        };
        m_dir.Add (entry);
    }

    int arc_count = Binary.BigEndian (m_index.ReadUInt16());
    int arc_index = -1;
    for (int i = 0; i < arc_count; ++i)
    {
        m_index.ReadUInt32();
        m_index.ReadUInt32();
        m_index.ReadUInt32();
        long arc_size = (long)Binary.BigEndian (m_index.ReadUInt32()) << 4;
        if (m_max_offset == arc_size)
            arc_index = i;
        m_index.ReadUInt64();
        m_index.Seek (16, SeekOrigin.Current);
    }

    count = Binary.BigEndian (m_index.ReadUInt16());
    if (count > 0)
        m_index.Seek (count * 24, SeekOrigin.Current);
    DeserializeTree();
    if (arc_count > 1 && arc_index != -1)
    {
        return m_dir.Where (e => (e as SxEntry).ArcIndex == arc_index).ToList();
    }
    return m_dir;
}
```

#### DeserializeTree

```csharp
void DeserializeTree (string path = "") {
    int count = Binary.BigEndian (m_index.ReadUInt16());
    int name_index = Binary.BigEndian (m_index.ReadInt32());
    int file_index = Binary.BigEndian (m_index.ReadInt32());
    var name = Path.Combine (path, m_name_list[name_index]);
    if (-1 == file_index)
    {
        for (int i = 0; i < count; ++i)
        {
            DeserializeTree (name);
        }
    }
    else
    {
        m_dir[file_index].Name = name;
        m_dir[file_index].Type = FormatCatalog.Instance.GetTypeFromName (name);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Experimental/SakanaGL/ArcSX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
