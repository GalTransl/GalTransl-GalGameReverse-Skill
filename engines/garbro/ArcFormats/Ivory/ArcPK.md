# Ivory / ArcPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PK/IVORY` / `GameRes.Formats.Ivory.PakOpener` | `pk` | `66504b20`, `66504b32` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int version = '2' == file.View.ReadByte (3) ? 2 : 1;` |
| `PakOpener.TryOpen` | `read_long = s => s.ReadInt64();` |
| `PakOpener.TryOpen` | `read_long = s => s.ReadUInt32();` |
| `PakOpener.TryOpen` | `var id_bytes = stream.ReadBytes (4);` |
| `PakOpener.TryOpen` | `stream.ReadUInt32();` |
| `PakOpener.TryOpen` | `int count = stream.ReadInt32();` |
| `PakOpener.TryOpen` | `uint key = stream.ReadUInt32();` |
| `PakOpener.TryOpen` | `var clst = stream.ReadBytes ((int)(section_size - header_size));` |
| `PakOpener.TryOpen` | `names = stream.ReadBytes ((int)(section_size - header_size));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ivory.PkEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public int  NameOffset ;
```

### GameRes.Formats.Ivory.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Signatures = new uint[] { 0x204B5066, 0x324B5066 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = '2' == file.View.ReadByte (3) ? 2 : 1;
    long base_offset = 0;
    List<Entry> dir = null;
    byte[] names = null;
    using (var stream = file.CreateStream())
    {
        Func<IBinaryStream, long> read_long;
        if (2 == version)
            read_long = s => s.ReadInt64();
        else
            read_long = s => s.ReadUInt32();

        stream.Position = 4;
        if (file.MaxOffset != read_long (stream))
            return null;
        for (;;)
        {
            long section_start = stream.Position;
            var id_bytes = stream.ReadBytes (4);
            if (0 == id_bytes.Length)
                break;
            var id = new AsciiString (id_bytes);
            var section_size = read_long (stream);
            var header_size = read_long (stream);
            if (section_size < 4 || header_size > section_size)
                return null;
            var content_pos = section_start + header_size;
            if ("cLST" == id)
            {
                stream.ReadUInt32();
                int count = stream.ReadInt32();
                if (!IsSaneCount (count))
                    return null;
                uint key = stream.ReadUInt32();
                stream.Position = content_pos;
                var clst = stream.ReadBytes ((int)(section_size - header_size));
                Decrypt (clst, key);
                dir = new List<Entry> (count);
                using (var index = new BinMemoryStream (clst))
                {
                    for (int i = 0; i < count; ++i)
                    {
                        var entry = new PkEntry {
                            NameOffset  = (int)read_long (index),
                            Offset      = (long)read_long (index),
                            Size        = (uint)read_long (index),
                        };
                        dir.Add (entry);
                    }
                }
            }
            else if ("cNAM" == id)
            {
                if (null == dir)
                    return null;
                stream.ReadUInt32();
                uint key = stream.ReadUInt32();
                stream.Position = content_pos;
                names = stream.ReadBytes ((int)(section_size - header_size));
                Decrypt (names, key);
            }
            else if ("cDAT" == id)
            {
                base_offset = content_pos;
            }
            stream.Position = section_start + section_size;
        }
    }
    if (null == dir || null == names || 0 == base_offset)
        return null;

    foreach (PkEntry entry in dir)
    {
        entry.Offset += base_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        var name = Binary.GetCString (names, entry.NameOffset);
        entry.Name = name;
        if (name.HasExtension (".px"))
            entry.Type = "audio";
        else
            entry.Type = FormatCatalog.Instance.GetTypeFromName (name);
    }
    return new ArcFile (file, this, dir);
}
```

#### Decrypt

```csharp
internal static void Decrypt (byte[] data, uint seed) {
    int length = data.Length / 4;
    if (0 == length)
        return;
    var ctl = new ushort[32];
    var key = new uint[32];

    for (int i = 0; i < 32; ++i)
    {
        uint code = 0;
        uint k = seed;
        for (int j = 0; j < 16; ++j)
        {
            code = (k ^ (k >> 1)) << 15 | (code & 0xFFFF) >> 1;
            k >>= 2;
        }
        key[i] = seed;
        ctl[i] = (ushort)code;
        seed = Binary.RotL (seed, 1);
    }
    unsafe
    {
        fixed (byte* data8 = data)
        {
            uint* data32 = (uint*)data8;
            for (int i = 0; i < length; ++i)
            {
                uint s = *data32;
                ushort code = ctl[i & 0x1F];
                uint d = 0;
                uint v3 = 3;
                uint v2 = 2;
                uint v1 = 1;
                for (int j = 0; j < 16; ++j)
                {
                    if (0 != (code & 1))
                    {
                        d |= (s & v1) << 1 | (s >> 1) & (v2 >> 1);
                    }
                    else
                    {
                        d |= s & v3;
                    }
                    code >>= 1;
                    v3 <<= 2;
                    v2 <<= 2;
                    v1 <<= 2;
                }
                *data32++ = d ^ key[i & 0x1F];
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Ivory/ArcPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
