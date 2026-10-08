# Dogenzaka / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/Dogenzaka` / `GameRes.Formats.Dogenzaka.BinOpener` | `bin` | 无固定签名或来源表达式未解析 | `False` |
| `BIN/Dogenzaka/2` / `GameRes.Formats.Dogenzaka.GamedatOpener` | `bin` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `BinOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset),` |
| `BinOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset+4),` |
| `BinOpener.TryOpen` | `var n = file.View.ReadInt32 (entry.Offset);` |
| `BinOpener.TryOpen` | `var offset = file.View.ReadUInt32 (entry.Offset+4);` |
| `BinOpener.TryOpen` | `var size   = file.View.ReadUInt32 (entry.Offset+8);` |
| `BinOpener.TryOpen` | `var res = AutoEntry.DetectFileType (file.View.ReadUInt32 (entry.Offset));` |
| `GamedatOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `GamedatOpener.TryOpen` | `uint next_offset = file.View.ReadUInt32 (index_offset);` |
| `GamedatOpener.TryOpen` | `next_offset = base_offset + file.View.ReadUInt32 (index_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Dogenzaka.BinOpener

继承/接口：`ArchiveFormat`。

#### BinOpener

```csharp
public BinOpener () {
    Extensions = new string[] { "bin" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    int index_offset = 4;
    int index_end = 4 + 8 * count;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new PackedEntry
        {
            Offset = file.View.ReadUInt32 (index_offset),
            Size   = file.View.ReadUInt32 (index_offset+4),
        };
        if (entry.Offset < index_end || !entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Name = string.Format ("{0}#{1:D5}", base_name, i);
        dir.Add (entry);
        index_offset += 8;
    }
    foreach (PackedEntry entry in dir)
    {
        var n = file.View.ReadInt32 (entry.Offset);
        if (n <= 0)
            return null;
        var offset = file.View.ReadUInt32 (entry.Offset+4);
        var size   = file.View.ReadUInt32 (entry.Offset+8);
        entry.Offset += offset;
        entry.Size = size & 0x3FFFFFFF;
        entry.IsPacked = 2 != (size >> 30);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        var res = AutoEntry.DetectFileType (file.View.ReadUInt32 (entry.Offset));
        if (res != null)
            entry.ChangeType (res);
    }
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

### GameRes.Formats.Dogenzaka.GamedatOpener

继承/接口：`ArchiveFormat`。

#### GamedatOpener

```csharp
public GamedatOpener () {
    Extensions = new string[] { "bin" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count-1))
        return null;
    uint base_offset = (uint)(4 + 4 * count);
    if (base_offset >= file.MaxOffset)
        return null;

    uint index_offset = 4;
    uint next_offset = file.View.ReadUInt32 (index_offset);
    if (next_offset != 0)
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    next_offset = base_offset;
    --count;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        index_offset += 4;
        var name = string.Format ("{0}#{1:D4}", base_name, i);
        var entry = AutoEntry.Create (file, next_offset, name);
        next_offset = base_offset + file.View.ReadUInt32 (index_offset);
        entry.Size = next_offset - (uint)entry.Offset;
        if (0 == entry.Size || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Dogenzaka/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
