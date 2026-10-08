# Abel / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/ADVENGINE` / `GameRes.Formats.Abel.ArcOpener` | `` | `61726300` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `ArcOpener.TryOpen` | `uint base_offset = file.View.ReadUInt32 (0xC);` |
| `ArcOpener.TryOpen` | `uint packed_size = file.View.ReadUInt32 (0x10);` |
| `ArcOpener.TryOpen` | `int index_size = file.View.ReadInt32 (0x14);` |
| `ArcOpener.TryOpen` | `entry.Offset = index.ReadUInt32() + base_offset;` |
| `ArcOpener.TryOpen` | `entry.Size   = index.ReadUInt32();` |
| `ArcOpener.OpenEntry` | `&& arc.File.View.AsciiEqual (entry.Offset, "CMP\0"))` |
| `ArcOpener.OpenEntry` | `&& arc.File.View.AsciiEqual (entry.Offset, "ACD\0"))` |
| `ArcOpener.OpenAcdEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `ArcOpener.OpenCmpEntry` | `uint offset = arc.File.View.ReadUInt32 (entry.Offset+8);` |
| `ArcOpener.OpenCmpEntry` | `if (arc.File.View.ReadByte (cmp_offset) == 0)` |
| `ArcOpener.OpenCmpEntry` | `uint packed_size = arc.File.View.ReadUInt32 (cmp_offset+5);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Abel.ArcOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const int IndexEntrySize = 0x26 ;
```

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint base_offset = file.View.ReadUInt32 (0xC);
    if (base_offset <= 0x18 || base_offset >= file.MaxOffset)
        return null;
    uint packed_size = file.View.ReadUInt32 (0x10);
    int index_size = file.View.ReadInt32 (0x14);
    if (packed_size > file.MaxOffset || index_size / IndexEntrySize != count)
        return null;
    var name_buffer = new byte[30];
    using (var packed = file.CreateStream (0x18, packed_size))
    using (var lzss = new LzssStream (packed))
    using (var index = new ArcView.Reader (lzss))
    {
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            if (name_buffer.Length != index.Read (name_buffer, 0, name_buffer.Length))
                return null;
            var name = Binary.GetCString (name_buffer, 0, name_buffer.Length);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            if (name.HasExtension (".acd"))
                entry.Type = "script";
            entry.Offset = index.ReadUInt32() + base_offset;
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
    if (entry.Size > 12 && entry.Name.HasExtension (".cmp")
        && arc.File.View.AsciiEqual (entry.Offset, "CMP\0"))
        return OpenCmpEntry (arc, entry);
    if (entry.Size > 8 && entry.Name.HasExtension (".acd")
        && arc.File.View.AsciiEqual (entry.Offset, "ACD\0"))
        return OpenAcdEntry (arc, entry);
    return base.OpenEntry (arc, entry);
}
```

#### OpenAcdEntry

```csharp
Stream OpenAcdEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    for (int i = 8; i < data.Length; ++i)
    {
        data[i] = (byte)(0xFF - data[i]);
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### OpenCmpEntry

```csharp
Stream OpenCmpEntry (ArcFile arc, Entry entry) {
    uint offset = arc.File.View.ReadUInt32 (entry.Offset+8);
    if (offset >= entry.Size)
        return base.OpenEntry (arc, entry);
    long cmp_offset = entry.Offset + offset;
    if (arc.File.View.ReadByte (cmp_offset) == 0)
    {
        uint packed_size = arc.File.View.ReadUInt32 (cmp_offset+5);
        if (packed_size == entry.Size - (offset+0x11))
        {
            var input = arc.File.CreateStream (cmp_offset+0x11, packed_size);
            return new LzssStream (input);
        }
    }
    return arc.File.CreateStream (entry.Offset+offset, entry.Size-offset);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Abel/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
