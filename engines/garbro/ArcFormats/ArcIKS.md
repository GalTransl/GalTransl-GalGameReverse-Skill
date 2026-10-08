# ArcFormats / ArcIKS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `IKS` / `GameRes.Formats.X.IksOpener` | `iks` | `4e505352` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IksOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `IksOpener.TryOpen` | `byte name_length = Math.Min ((byte)0x17, file.View.ReadByte (index_offset));` |
| `IksOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x20);` |
| `IksOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x1C);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.X.IksOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (count <= 0 || count > 0xfffff)
        return null;
    uint index_offset = 0x10;
    uint index_size = (uint)(0x28 * count);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    long data_offset = index_offset + index_size;
    var dir = new List<Entry> (count);
    var name_buffer = new byte[0x18];
    for (int i = 0; i < count; ++i)
    {
        byte name_length = Math.Min ((byte)0x17, file.View.ReadByte (index_offset));
        if (name_length > name_buffer.Length)
            return null;
        file.View.Read (index_offset+1, name_buffer, 0, name_length);
        string name = Encodings.cp932.GetString (name_buffer, 0, name_length);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x20);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x1C);
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
    byte key = KnownKeys.First().Value;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new XoredStream (input, key);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ArcIKS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
