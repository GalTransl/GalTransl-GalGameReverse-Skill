# Propeller / ArcMPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MPK` / `GameRes.Formats.Propeller.MpkOpener` | `mpk` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MpkOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0);` |
| `MpkOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `MpkOpener.TryOpen` | `var index = file.View.ReadBytes (index_offset, index_size);` |
| `MpkOpener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, current+0x20);` |
| `MpkOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (index, current+0x24);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Propeller.MpkOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_offset = file.View.ReadUInt32 (0);
    int count = file.View.ReadInt32 (4);
    if (index_offset < 8 || index_offset >= file.MaxOffset || !IsSaneCount (count))
        return null;
    uint index_size = (uint)count * 0x28u;
    if (index_size > file.MaxOffset - index_offset)
        return null;
    var index = file.View.ReadBytes (index_offset, index_size);

    byte key = index[0x1F];
    for (int i = 0; i < index.Length; ++i)
        index[i] ^= key;

    int current = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_offset = '\\' == index[current] ? 1 : 0;
        var name = Binary.GetCString (index, current+name_offset, 0x20-name_offset);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = LittleEndian.ToUInt32 (index, current+0x20);
        entry.Size   = LittleEndian.ToUInt32 (index, current+0x24);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        current += 0x28;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (!entry.Name.HasExtension (".msc")
        || 0x88 != input.PeekByte())
        return input;
    return new XoredStream (input, 0x88);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Propeller/ArcMPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
