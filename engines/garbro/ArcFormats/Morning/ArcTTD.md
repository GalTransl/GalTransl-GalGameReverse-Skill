# Morning / ArcTTD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `TTD` / `GameRes.Formats.Morning.TtdOpener` | `ttd` | `2e465243` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `TtdOpener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `TtdOpener.TryOpen` | `uint key = file.View.ReadUInt32 (4);` |
| `TtdOpener.TryOpen` | `var index = file.View.ReadBytes (0x14, (uint)index_size);` |
| `TtdOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (index, index_offset);` |
| `TtdOpener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `TtdOpener.OpenEntry` | `if (entry.Size <= 8 \|\| !arc.File.View.AsciiEqual (entry.Offset, "DSFF"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Morning.TtdOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count))
        return null;
    uint key = file.View.ReadUInt32 (4);
    int index_size = count * 0x2C;
    var index = file.View.ReadBytes (0x14, (uint)index_size);
    if (index.Length != index_size)
        return null;
    Decrypt (index, key);
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, index_offset+12, 0x20);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = LittleEndian.ToUInt32 (index, index_offset);
        entry.Offset = LittleEndian.ToUInt32 (index, index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x2C;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size <= 8 || !arc.File.View.AsciiEqual (entry.Offset, "DSFF"))
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset+8, entry.Size-8);
    var lzss = new LzssStream (input);
    lzss.Config.FrameInitPos = 0xFF0;
    return lzss;
}
```

#### Decrypt

```csharp
unsafe void Decrypt (byte[] data, uint key) {
    fixed (byte* data8 = data)
    {
        uint* data32 = (uint*)data8;
        for (int length = data.Length / 4; length > 0; --length)
            *data32++ ^= key;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Morning/ArcTTD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
