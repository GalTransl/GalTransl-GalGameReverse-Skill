# Duke / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/DUKE` / `GameRes.Formats.Duke.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (0) ^ 0xfa261efb);` |
| `DatOpener.TryOpen` | `var buffer = file.View.ReadBytes (index_offset, 0x20);` |
| `DatOpener.TryOpen` | `entry.Size   = (uint)(file.View.ReadUInt32 (index_offset+0x20) ^ 0xfa261efb);` |
| `DatOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x24);` |
| `DatOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Duke.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;

    int count = (int)(file.View.ReadUInt32 (0) ^ 0xfa261efb);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 4;
    uint data_offset = index_offset + (uint)count * 0x28u;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var buffer = file.View.ReadBytes (index_offset, 0x20);
        for (int counter = 0; counter < 0x20; counter++)
        {
            buffer[counter] = (byte)(buffer[counter] ^ counter * 5 + 172);
        }
        var name = Binary.GetCString (buffer, 0);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = (uint)(file.View.ReadUInt32 (index_offset+0x20) ^ 0xfa261efb);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x24);
        if (entry.Offset < data_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x28;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    var name = Encodings.cp932.GetBytes (entry.Name);
    int length = name.Length;
    for (int i = 0; i < entry.Size && i < 0x2c00; i += length)
    {
        for (int j = 0; j < length && j < entry.Size - i; j++)
        {
            data[i + j] = (byte)(data[i + j] ^ name[j] + i + j);
        }
    }
    return new BinMemoryStream (data);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Duke/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
