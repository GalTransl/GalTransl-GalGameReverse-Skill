# AdvSys / ArcGR2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GR2/PACK` / `GameRes.Formats.UMeSoft.Gr2Opener` | `gr2`, `vic`, `pac` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Gr2Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Gr2Opener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (8);` |
| `Gr2Opener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `Gr2Opener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x10);` |
| `Gr2Opener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x14);` |
| `Gr2Opener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "LL5\0"))` |
| `Gr2Opener.LL5Decompress` | `int count = input.ReadInt8();` |
| `Gr2Opener.LL5Decompress` | `byte v = input.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.UMeSoft.Gr2Opener

继承/接口：`ArchiveFormat`。

#### Gr2Opener

```csharp
public Gr2Opener () {
    Extensions = new string[] { "gr2", "vic", "pac" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    uint data_offset = file.View.ReadUInt32 (8);
    if (data_offset < 0x10 || data_offset >= file.MaxOffset)
        return null;
    bool is_gr2 = file.Name.HasExtension ("gr2");

    uint index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x10);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x14);
        if (entry.Offset < data_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        if (is_gr2)
            entry.Type = "image";
        dir.Add (entry);
        index_offset += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!arc.File.View.AsciiEqual (entry.Offset, "LL5\0"))
        return base.OpenEntry (arc, entry);
    using (var input = arc.File.CreateStream (entry.Offset+4, entry.Size-4))
    {
        var output = new MemoryStream();
        LL5Decompress (input, output);
        output.Position = 0;
        return output;
    }
}
```

#### LL5Decompress

```csharp
void LL5Decompress (IBinaryStream input, Stream output) {
    var buffer = new byte[0x100];
    while (input.PeekByte() != -1)
    {
        int count = input.ReadInt8();
        if (count < 0)
        {
            count = -count;
            input.Read (buffer, 0, count);
            output.Write (buffer, 0, count);
        }
        else
        {
            byte v = input.ReadUInt8();
            for (int i = 0; i < count; ++i)
                buffer[i] = v;
            output.Write (buffer, 0, count);
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/AdvSys/ArcGR2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
