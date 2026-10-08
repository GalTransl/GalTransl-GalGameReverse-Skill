# Origin / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/HED` / `GameRes.Formats.Origin.HedDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `HedDatOpener.TryOpen` | `int name_length = hed.ReadUInt8();` |
| `HedDatOpener.TryOpen` | `Offset = hed.ReadUInt32(),` |
| `HedDatOpener.DetectFileTypes` | `if (buffer.AsciiEqual (0xD, "OggS"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Origin.HedDatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension ("DAT"))
        return null;
    var hed_name = Path.ChangeExtension (file.Name, "HED");
    if (!VFS.FileExists (hed_name))
        return null;
    using (var hed = VFS.OpenBinaryStream (hed_name))
    {
        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        var dir = new List<Entry>();
        var name_buffer = new byte[0x100];
        while (hed.PeekByte() != -1)
        {
            int name_length = hed.ReadUInt8();
            string name;
            if (name_length != 0)
            {
                if (hed.Read (name_buffer, 0, name_length) != name_length)
                    return null;
                for (int i = 0; i < name_length; ++i)
                    name_buffer[i] ^= 0xFF;
                name = Binary.GetCString (name_buffer, 0, name_length);
            }
            else
            {
                name = string.Format ("{0}#{1:D4}", base_name, dir.Count);
            }
            var entry = new Entry {
                Name = name,
                Offset = hed.ReadUInt32(),
            };
            if (entry.Offset > file.MaxOffset)
                return null;
            dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        AdjustSizes (dir, file.MaxOffset);
        DetectFileTypes (dir, file);
        return new ArcFile (file, this, dir);
    }
}
```

#### AdjustSizes

```csharp
void AdjustSizes (List<Entry> dir, long arc_length) {
    var last = dir[0];
    for (int i = 1; i < dir.Count; ++i)
    {
        var next = dir[i];
        last.Size = (uint)(next.Offset - last.Offset);
        last = next;
    }
    last.Size = (uint)(arc_length - last.Offset);
}
```

#### DetectFileTypes

```csharp
void DetectFileTypes (List<Entry> dir, ArcView file) {
    bool is_mask = VFS.IsPathEqualsToFileName (file.Name, "MASK.DAT");
    var buffer = new byte[0x11];
    foreach (var entry in dir)
    {
        file.View.Read (entry.Offset, buffer, 0, 0x11);
        if (buffer.AsciiEqual (0xD, "OggS"))
        {
            entry.ChangeType (OggAudio.Instance);
            entry.Offset += 0xD;
            entry.Size -= 0xD;
        }
        else if (is_mask || buffer[0] <= 1 && buffer[1] > 0 && buffer[1] <= 3)
            entry.Type = "image";
    }
}
```

## 配套算法与外部条件

- [ArcFormats/AudioOGG.cs](../AudioOGG.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Origin/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
