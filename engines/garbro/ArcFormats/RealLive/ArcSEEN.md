# RealLive / ArcSEEN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SEEN` / `GameRes.Formats.RealLive.SeenOpener` | `` | `5041434c` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SeenOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `SeenOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `SeenOpener.TryOpen` | `entry.Offset        = file.View.ReadUInt32 (index_offset+0x10);` |
| `SeenOpener.TryOpen` | `entry.Size          = file.View.ReadUInt32 (index_offset+0x14);` |
| `SeenOpener.TryOpen` | `entry.UnpackedSize  = file.View.ReadUInt32 (index_offset+0x18);` |
| `SeenOpener.TryOpen` | `entry.IsPacked      = file.View.ReadUInt32 (index_offset+0x1C) != 0;` |
| `SeenOpener.OpenEntry` | `int unpacked_size = input.ReadInt32();` |
| `SeenOpener.LzDecompress` | `bits = input.ReadUInt8();` |
| `SeenOpener.LzDecompress` | `output[dst++] = input.ReadUInt8();` |
| `SeenOpener.LzDecompress` | `int offset = input.ReadUInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.RealLive.SeenOpener

继承/接口：`ArchiveFormat`。

#### SeenOpener

```csharp
public SeenOpener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 0x20;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset        = file.View.ReadUInt32 (index_offset+0x10);
        entry.Size          = file.View.ReadUInt32 (index_offset+0x14);
        entry.UnpackedSize  = file.View.ReadUInt32 (index_offset+0x18);
        entry.IsPacked      = file.View.ReadUInt32 (index_offset+0x1C) != 0;
        if (entry.Size > 0)
        {
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        index_offset += 0x20;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked || input.Signature != 0x4B434150)
        return input;
    using (input)
    {
        input.Position = 8;
        int unpacked_size = input.ReadInt32();
        var output = new byte[unpacked_size];
        input.Position = 0x10;
        LzDecompress (input, output);
        return new BinMemoryStream (output, entry.Name);
    }
}
```

#### LzDecompress

```csharp
internal static void LzDecompress (IBinaryStream input, byte[] output) {
    int dst = 0;
    int bits = 0;
    int mask = 0;
    while (dst < output.Length)
    {
        mask >>= 1;
        if (0 == mask)
        {
            bits = input.ReadUInt8();
            mask = 0x80;
        }
        if (0 != (bits & mask))
        {
            output[dst++] = input.ReadUInt8();
        }
        else
        {
            int offset = input.ReadUInt16();
            int count = (offset & 0xF) + 2;
            offset >>= 4;
            Binary.CopyOverlapped (output, dst-offset-1, dst, count);
            dst += count;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/RealLive/ArcSEEN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
