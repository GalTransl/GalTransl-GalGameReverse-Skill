# GameSystem / ArcPureMail：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/PUREMAIL` / `GameRes.Formats.GameSystem.PmDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PmDatOpener.TryOpen` | `uint packed_size   = file.View.ReadUInt32 (file.MaxOffset-12) ^ 0xF0F0F0F0;` |
| `PmDatOpener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (file.MaxOffset-8)  ^ 0xF0F0F0F0;` |
| `PmDatOpener.TryOpen` | `int flags = index.ReadInt32();` |
| `PmDatOpener.TryOpen` | `var name = index.ReadCString (0x40);` |
| `PmDatOpener.TryOpen` | `entry.Offset = index.ReadUInt32();` |
| `PmDatOpener.TryOpen` | `entry.Size   = index.ReadUInt32();` |
| `PmDatOpener.TryOpen` | `entry.UnpackedSize = index.ReadUInt32();` |
| `PmDatOpener.OpenEntry` | `unpacked_size = input.ReadUInt32();` |
| `PmDatOpener.LzUnpack` | `bits = input.ReadByte();` |
| `PmDatOpener.LzUnpack` | `int b = input.ReadByte();` |
| `PmDatOpener.LzUnpack` | `int offset = input.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.GameSystem.PmDatEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public bool StoredSize ;
```

### GameRes.Formats.GameSystem.PmDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset <= 12 || file.MaxOffset > uint.MaxValue)
        return null;
    uint packed_size   = file.View.ReadUInt32 (file.MaxOffset-12) ^ 0xF0F0F0F0;
    uint unpacked_size = file.View.ReadUInt32 (file.MaxOffset-8)  ^ 0xF0F0F0F0;
    const uint entry_record_size = 0x50;
    int count = (int)(unpacked_size / entry_record_size);
    if (unpacked_size % entry_record_size != 0 || packed_size >= file.MaxOffset || !IsSaneCount (count))
        return null;

    var unpacked = new byte[unpacked_size];
    using (var packed = file.CreateStream (file.MaxOffset-12-packed_size, packed_size))
        LzUnpack (packed, unpacked);
    using (var index = new BinMemoryStream (unpacked))
    {
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            int flags = index.ReadInt32();
            var name = index.ReadCString (0x40);
            var entry = FormatCatalog.Instance.Create<PmDatEntry> (name);
            entry.Offset = index.ReadUInt32();
            entry.Size   = index.ReadUInt32();
            entry.UnpackedSize = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            if (entry.Name.HasAnyOfExtensions ("CRGB", "CHAR", "rol", "edg"))
                entry.Type = "image";
            entry.IsPacked = (flags & 0xFF0000) != 0;
            entry.StoredSize = (flags & 0x2000000) != 0;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PmDatEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        var unpacked_size = pent.UnpackedSize;
        if (pent.StoredSize)
        {
            unpacked_size = input.ReadUInt32();
            pent.UnpackedSize = unpacked_size;
        }
        var output = new byte[unpacked_size];
        LzUnpack (input, output);
        return new BinMemoryStream (output);
    }
}
```

#### LzUnpack

```csharp
void LzUnpack (IBinaryStream input, byte[] output) {
    var frame = new byte[0x1000];
    int dst = 0;
    int bits = 0;
    int mask = 0;
    int frame_pos = 0xFEE;
    while (dst < output.Length)
    {
        mask >>= 1;
        if (0 == mask)
        {
            bits = input.ReadByte();
            if (-1 == bits)
                break;
            mask = 0x80;
        }
        if (0 == (bits & mask))
        {
            int b = input.ReadByte();
            if (-1 == b)
                break;
            output[dst++] = (byte)b;
            frame[frame_pos++ & 0xFFF] = (byte)b;
        }
        else
        {
            int offset = input.ReadUInt16();
            int count = (offset & 0xF) + 3;
            offset >>= 4;
            while (count --> 0 && dst < output.Length)
            {
                byte v = frame[offset++ & 0xFFF];
                frame[frame_pos++ & 0xFFF] = v;
                output[dst++] = v;
            }
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/GameSystem/ArcPureMail.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
