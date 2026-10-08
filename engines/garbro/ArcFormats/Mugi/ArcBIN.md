# Mugi / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/MUGI` / `GameRes.Formats.Mugi.BinOpener` | `bin` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_pos);` |
| `BinOpener.TryOpen` | `offset = file.View.ReadUInt32 (index_pos);` |
| `BinOpener.TryOpen` | `var name = file.View.ReadString (name_pos, 0x10);` |
| `BinOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (size_pos);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Mugi.BinOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    const uint index_size = 0x8000 + 0x4000;
    if (file.MaxOffset <= index_size)
        return null;
    file.View.Reserve (0, index_size);
    uint index_pos = 0x8000;
    uint offset = file.View.ReadUInt32 (index_pos);
    if (offset != index_size)
        return null;
    uint[] offsets = new uint[0x800];
    int count = 0;
    while (offset != file.MaxOffset)
    {
        if (count == offsets.Length)
            return null;
        offsets[count++] = offset;
        index_pos += 4;
        offset = file.View.ReadUInt32 (index_pos);
        if (offset < offsets[count-1] || offset > file.MaxOffset)
            return null;
    }
    offsets[count--] = offset;
    uint name_pos = 0;
    uint size_pos = 0xA000;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (name_pos, 0x10);
        var entry = Create<PackedEntry> (name);
        entry.Offset = offsets[i];
        entry.Size = (uint)(offsets[i+1] - offsets[i]);
        entry.UnpackedSize = file.View.ReadUInt32 (size_pos);
        entry.IsPacked = entry.Size != entry.UnpackedSize;
        dir.Add (entry);
        name_pos += 0x10;
        size_pos += 4;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (pent.IsPacked)
        input = new LzssStream (input);
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Mugi/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
