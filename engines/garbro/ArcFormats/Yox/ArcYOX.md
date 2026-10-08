# Yox / ArcYOX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/YOX` / `GameRes.Formats.Yox.DatOpener` | `dat` | `594f5800` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `DatOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (current_offset);` |
| `DatOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (current_offset+4);` |
| `DatOpener.DetectFileTypes` | `uint signature = ReadUInt32 (file);` |
| `DatOpener.DetectFileTypes` | `if (0 != (2 & ReadUInt32 (file)))` |
| `DatOpener.DetectFileTypes` | `entry.UnpackedSize = ReadUInt32 (file);` |
| `DatOpener.DetectFileTypes` | `signature = ReadUInt32 (input);` |
| `DatOpener.ReadUInt32` | `static uint ReadUInt32 (Stream input) {` |
| `DatOpener.ReadUInt32` | `uint v = (uint)input.ReadByte();` |
| `DatOpener.ReadUInt32` | `v \|= (uint)input.ReadByte() << 8;` |
| `DatOpener.ReadUInt32` | `v \|= (uint)input.ReadByte() << 16;` |
| `DatOpener.ReadUInt32` | `v \|= (uint)input.ReadByte() << 24;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Yox.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_offset = file.View.ReadUInt32 (8);
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count) || index_offset >= file.MaxOffset)
        return null;

    var dir = new List<Entry> (count);
    Func<uint, bool> ReadIndex = entry_size => {
        uint current_offset = index_offset;
        for (int i = 0; i < count; ++i)
        {
            var entry = new PackedEntry { Name = i.ToString ("D5") };
            entry.Offset = file.View.ReadUInt32 (current_offset);
            entry.Size   = file.View.ReadUInt32 (current_offset+4);
            if (0 == entry.Size || !entry.CheckPlacement (file.MaxOffset))
                return false;
            dir.Add (entry);
            current_offset += entry_size;
        }
        return true;
    };
    if (!ReadIndex (8))
    {
        dir.Clear();
        if (!ReadIndex (0x10))
            return null;
    }
    using (var stream = file.CreateStream())
        DetectFileTypes (stream, dir);
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = base.OpenEntry (arc, entry);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

#### DetectFileTypes

```csharp
void DetectFileTypes (Stream file, IList<Entry> dir) {
    foreach (PackedEntry entry in dir)
    {
        file.Position = entry.Offset;
        uint signature = ReadUInt32 (file);
        IResource res = null;
        if (0x584F59 == signature)
        {
            if (0 != (2 & ReadUInt32 (file)))
            {
                entry.IsPacked = true;
                entry.UnpackedSize = ReadUInt32 (file);
                entry.Offset += 0x10;
                entry.Size   -= 0x10;
                file.Position = entry.Offset;
                using (var input = new ZLibStream (file, CompressionMode.Decompress, true))
                    signature = ReadUInt32 (input);
                res = AutoEntry.DetectFileType (signature);
            }
        }
        else
            res = AutoEntry.DetectFileType (signature);
        if (res != null)
        {
            entry.Name = Path.ChangeExtension (entry.Name, res.Extensions.FirstOrDefault());
            entry.Type = res.Type;
        }
    }
}
```

#### ReadUInt32

```csharp
static uint ReadUInt32 (Stream input) {
    uint v = (uint)input.ReadByte();
    v |= (uint)input.ReadByte() << 8;
    v |= (uint)input.ReadByte() << 16;
    v |= (uint)input.ReadByte() << 24;
    return v;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Yox/ArcYOX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
