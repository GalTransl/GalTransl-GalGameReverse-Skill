# Carriere / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/CARRIERE` / `GameRes.Formats.Carriere.ArcOpener` | `arc` | `879b948f` | `False` |
| `ARC/~ARCHIVE` / `GameRes.Formats.Carriere.ScenarioArcOpener` | `arc` | `beadbcb7` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `if (file.View.ReadUInt32 (4) != 0x869E919A)` |
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `ArcOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x104);` |
| `ArcOpener.TryOpen` | `entry.Offset        = file.View.ReadUInt32 (index_offset+0x104);` |
| `ArcOpener.TryOpen` | `entry.UnpackedSize  = file.View.ReadUInt32 (index_offset+0x108);` |
| `ArcOpener.TryOpen` | `entry.Size          = file.View.ReadUInt32 (index_offset+0x10C);` |
| `ScenarioArcOpener.TryOpen` | `if (file.View.ReadUInt32 (4) != 0xFFBAA9B6)` |
| `ScenarioArcOpener.TryOpen` | `uint index_length = file.View.ReadUInt32 (8);` |
| `ScenarioArcOpener.TryOpen` | `int count = index.ReadInt32();` |
| `ScenarioArcOpener.TryOpen` | `var name = index.ReadCString (0x104);` |
| `ScenarioArcOpener.TryOpen` | `entry.Offset = index.ReadUInt32() + data_offset;` |
| `ScenarioArcOpener.TryOpen` | `entry.Size   = index.ReadUInt32();` |
| `ScenarioArcOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+8);` |
| `ScenarioArcOpener.OpenDataStream` | `uint packed_size = file.View.ReadUInt32 (offset);` |
| `ScenarioArcOpener.OpenDataStream` | `int flags        = file.View.ReadInt32 (offset+4);` |
| `ScenarioArcOpener.OpenDataStream` | `int unpacked_size = file.View.ReadInt32 (offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Carriere.ArcOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt32 (4) != 0x869E919A)
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 0xC;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x104);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset        = file.View.ReadUInt32 (index_offset+0x104);
        entry.UnpackedSize  = file.View.ReadUInt32 (index_offset+0x108);
        entry.Size          = file.View.ReadUInt32 (index_offset+0x10C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = entry.UnpackedSize != entry.Size;
        dir.Add (entry);
        index_offset += 0x110;
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

### GameRes.Formats.Carriere.ScenarioArcOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadUInt32 (4) != 0xFFBAA9B6)
        return null;
    uint index_length = file.View.ReadUInt32 (8);
    using (var index_s = OpenDataStream (file, 8))
    using (var index = BinaryStream.FromStream (index_s, file.Name))
    {
        int count = index.ReadInt32();
        if (!IsSaneCount (count))
            return null;
        uint data_offset = 8 + index_length;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var name = index.ReadCString (0x104);
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset = index.ReadUInt32() + data_offset;
            entry.Size   = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = OpenDataStream (arc.File, entry.Offset);
    var pent = entry as PackedEntry;
    if (pent != null && !pent.IsPacked)
    {
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+8);
    }
    return input;
}
```

#### OpenDataStream

```csharp
internal Stream OpenDataStream (ArcView file, long offset) {
    uint packed_size = file.View.ReadUInt32 (offset);
    int flags        = file.View.ReadInt32 (offset+4);
    int unpacked_size = file.View.ReadInt32 (offset+8);
    Stream input = file.CreateStream (offset+12, packed_size-12);
    if ((flags & 1) != 0)
    {
        input = new XoredStream (input, 0xFF);
    }
    if ((flags & 2) != 0)
    {
        input = new LzssStream (input);
    }
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Carriere/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
