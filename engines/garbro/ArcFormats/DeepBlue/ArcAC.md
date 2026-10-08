# DeepBlue / ArcAC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AC` / `GameRes.Formats.DeepBlue.AcOpener` | `ac1`, `ac2`, `ac3`, `ac4`, `ac5` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AcOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `AcOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (4);` |
| `AcOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (8);` |
| `AcOpener.TryOpen` | `var index = file.View.ReadBytes (index_offset, (uint)count * 0x64);` |
| `AcOpener.TryOpen` | `entry.Size         = LittleEndian.ToUInt32 (index, offset + 0x40);` |
| `AcOpener.TryOpen` | `entry.Offset       = LittleEndian.ToUInt32 (index, offset + 0x44) + data_offset;` |
| `AcOpener.TryOpen` | `entry.IsPacked     = LittleEndian.ToUInt32 (index, offset + 0x48) == 1;` |
| `AcOpener.TryOpen` | `entry.UnpackedSize = LittleEndian.ToUInt32 (index, offset + 0x4C);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DeepBlue.AcOpener

继承/接口：`ArchiveFormat`。

#### AcOpener

```csharp
public AcOpener () {
    Extensions = new string[] { "ac1", "ac2", "ac3", "ac4", "ac5" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (4);
    uint data_offset = file.View.ReadUInt32 (8);
    if (index_offset + count * 0x64 != data_offset)
        return null;

    var index = file.View.ReadBytes (index_offset, (uint)count * 0x64);
    for (int i = 0; i < index.Length; i++)
    {
        index[i] = Binary.RotByteL ((byte)(index[i] ^ 0xFF), 4);
    }

    int offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; i++)
    {
        var name = Binary.GetCString (index, offset, 0x40);
        var entry = Create<PackedEntry> (name);
        entry.Size         = LittleEndian.ToUInt32 (index, offset + 0x40);
        entry.Offset       = LittleEndian.ToUInt32 (index, offset + 0x44) + data_offset;
        entry.IsPacked     = LittleEndian.ToUInt32 (index, offset + 0x48) == 1;
        entry.UnpackedSize = LittleEndian.ToUInt32 (index, offset + 0x4C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        offset += 0x64;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (null == pent || !pent.IsPacked)
        return input;
    return new LzssStream (input);
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/DeepBlue/ArcAC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
