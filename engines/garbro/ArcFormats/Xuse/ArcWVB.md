# Xuse / ArcWVB：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WVB` / `GameRes.Formats.Xuse.WvbOpener` | `wvb` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `WvbOpener.TryOpen` | `int first_offset = file.View.ReadInt32 (4) - 1;` |
| `WvbOpener.TryOpen` | `uint fmt_size = file.View.ReadUInt32 (first_offset);` |
| `WvbOpener.TryOpen` | `if (!file.View.AsciiEqual (first_offset+fmt_size+4, "data"))` |
| `WvbOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_pos+4);` |
| `WvbOpener.TryOpen` | `Size = file.View.ReadUInt32 (index_pos) - 8,` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Xuse.WvbOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int first_offset = file.View.ReadInt32 (4) - 1;
    if (first_offset < 8 || first_offset >= file.MaxOffset)
        return null;
    int count = first_offset / 8;
    if ((first_offset & 7) != 0 || !IsSaneCount (count))
        return null;
    uint fmt_size = file.View.ReadUInt32 (first_offset);
    if (!file.View.AsciiEqual (first_offset+fmt_size+4, "data"))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_pos = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_pos+4);
        if (0 == offset)
            break;
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D2}", base_name, i),
            Type = "audio",
            Size = file.View.ReadUInt32 (index_pos) - 8,
            Offset = offset - 1,
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Size += 16;
        dir.Add (entry);
        index_pos += 8;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var header = new byte[0x10];
    LittleEndian.Pack (AudioFormat.Wav.Signature, header, 0);
    LittleEndian.Pack (entry.Size - 8u, header, 4);
    LittleEndian.Pack (0x45564157, header, 8);
    LittleEndian.Pack (0x20746d66, header, 12);
    var data = arc.File.CreateStream (entry.Offset, entry.Size - 16);
    return new PrefixStream (header, data);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Xuse/ArcWVB.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
