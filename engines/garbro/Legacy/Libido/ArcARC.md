# Libido / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/LIBIDO` / `GameRes.Formats.Libido.ArcOpener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `ArcOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x14);` |
| `ArcOpener.TryOpen` | `entry.Size         = file.View.ReadUInt32 (index_offset+0x18);` |
| `ArcOpener.TryOpen` | `entry.Offset       = file.View.ReadUInt32 (index_offset+0x1C);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Libido.ArcOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;

    const int name_buf_size = 0x14;
    var name_buf = new byte[name_buf_size];
    var is_name_encrypted = new Lazy<bool> (() => -1 != Array.IndexOf<byte> (name_buf, 0xFF, 0, name_buf_size));
    uint index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        file.View.Read (index_offset, name_buf, 0, name_buf_size);
        int j;
        if (is_name_encrypted.Value)
        {
            for (j = 0; j < name_buf_size; ++j)
            {
                name_buf[j] ^= 0xFF;
                if (0 == name_buf[j])
                    break;
            }
        }
        else
            j = Array.IndexOf<byte> (name_buf, 0, 0, name_buf_size);
        if (j <= 0 || -1 != Array.IndexOf<byte> (name_buf, 0xFF, 0, j))
            return null;
        var name = Encodings.cp932.GetString (name_buf, 0, j);
        var entry = Create<PackedEntry> (name);
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x14);
        entry.Size         = file.View.ReadUInt32 (index_offset+0x18);
        entry.Offset       = file.View.ReadUInt32 (index_offset+0x1C);
        if (entry.Offset <= index_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = entry.Size != entry.UnpackedSize;
        dir.Add (entry);
        index_offset += 0x20;
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

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Libido/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
