# Yaneurao / ArcSDA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SDA/yane` / `GameRes.Formats.Yaneurao.SdaOpener` | `sda` | `53514441` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SdaOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "SQDARC"))` |
| `SdaOpener.TryOpen` | `int dir_count = file.View.ReadInt32 (0x10);` |
| `SdaOpener.TryOpen` | `uint dir_offset = file.View.ReadUInt32 (index_offset);` |
| `SdaOpener.TryOpen` | `int file_count = file.View.ReadInt32 (index_offset+4);` |
| `SdaOpener.TryOpen` | `var dir_name = file.View.ReadString (index_offset+8, 10);` |
| `SdaOpener.TryOpen` | `var ext = file.View.ReadString (index_offset+0x12, 4);` |
| `SdaOpener.TryOpen` | `var name = file.View.ReadString (dir_offset, 0x28);` |
| `SdaOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (dir_offset+0x28);` |
| `SdaOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (dir_offset+0x2C);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Yaneurao.SdaOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "SQDARC"))
        return null;
    int dir_count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (dir_count))
        return null;
    var dir = new List<Entry>();
    uint index_offset = 0x14;
    for (int i = 0; i < dir_count; ++i)
    {
        uint dir_offset = file.View.ReadUInt32 (index_offset);
        int file_count = file.View.ReadInt32 (index_offset+4);
        var dir_name = file.View.ReadString (index_offset+8, 10);
        var ext = file.View.ReadString (index_offset+0x12, 4);
        for (int j = 0; j < file_count; ++j)
        {
            var name = file.View.ReadString (dir_offset, 0x28);
            name = Path.Combine (dir_name, name);
            name = Path.ChangeExtension (name, ext);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = file.View.ReadUInt32 (dir_offset+0x28);
            entry.Size   = file.View.ReadUInt32 (dir_offset+0x2C);
            dir_offset += 0x30;
            dir.Add (entry);
        }
        index_offset += 0x18;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    return new LzssStream (input);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Yaneurao/ArcSDA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
