# Softpal / ArcPAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/AMUSE` / `GameRes.Formats.Softpal.Pac2Opener` | `pac` | `50414320` | `False` |
| `PAC/SOFTPAL` / `GameRes.Formats.Softpal.PacOpener` | `pac` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PacOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `PacOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (index_offset+name_length+4);` |
| `PacOpener.TryOpen` | `first_offset = file.View.ReadUInt32 (index_offset+name_length+4);` |
| `PacOpener.ReadIndex` | `var name = file.View.ReadString (index_offset, name_length);` |
| `PacOpener.ReadIndex` | `entry.Size   = file.View.ReadUInt32 (index_offset);` |
| `PacOpener.ReadIndex` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |
| `PacOpener.OpenEntry` | `\|\| '$' != arc.File.View.ReadByte (entry.Offset))` |
| `PacOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `Pac2Opener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `Pac2Opener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (index_offset+name_length+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Softpal.PacOpener

继承/接口：`ArchiveFormat`。

#### PacOpener

```csharp
public PacOpener () {
    Extensions = new string[] { "pac" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 0x3FE;
    uint name_length = 0x20;
    uint first_offset = file.View.ReadUInt32 (index_offset+name_length+4);
    if (first_offset != index_offset + (uint)count*(name_length+8))
    {
        name_length = 0x10;
        first_offset = file.View.ReadUInt32 (index_offset+name_length+4);
        if (first_offset != index_offset + (uint)count*(name_length+8))
            return null;
    }
    if (first_offset >= file.MaxOffset)
        return null;
    return ReadIndex (file, count, index_offset, name_length);
}
```

#### ReadIndex

```csharp
protected ArcFile ReadIndex (ArcView file, int count, uint index_offset, uint name_length) {
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, name_length);
        index_offset += name_length;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if ("image" == entry.Type || "audio" == entry.Type || entry.Size <= 16
        || '$' != arc.File.View.ReadByte (entry.Offset))
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    int count = (data.Length - 16) / 4;
    if (count > 0)
    {
        unsafe
        {
            fixed (byte* data8 = &data[16])
            {
                uint* data32 = (uint*)data8;
                int shift = 4;
                for (uint* data_end = data32 + count; data32 != data_end; ++data32)
                {
                    byte* byte_ptr = (byte*)data32;
                    *byte_ptr = Binary.RotByteL (*byte_ptr, shift++);
                    *data32 ^= 0x084DF873u ^ 0xFF987DEEu;
                }
            }
        }
    }
    return new BinMemoryStream (data, entry.Name);
}
```

### GameRes.Formats.Softpal.Pac2Opener

继承/接口：`PacOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 0x804;
    uint name_length = 0x20;
    uint first_offset = file.View.ReadUInt32 (index_offset+name_length+4);
    if (first_offset != index_offset + (uint)count*(name_length+8))
        return null;

    return ReadIndex (file, count, index_offset, name_length);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Softpal/ArcPAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
