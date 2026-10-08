# Tsd / ArcMCD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MCD/TSD` / `GameRes.Formats.Tsd.McdOpener` | `mcd` | `4f4c4820` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `McdOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "for Win"))` |
| `McdOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (file.MaxOffset-8);` |
| `McdOpener.TryOpen` | `int count = file.View.ReadInt32 (file.MaxOffset-4);` |
| `McdOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset),` |
| `McdOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset+4),` |
| `McdOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tsd.McdOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "for Win"))
        return null;
    uint index_offset = file.View.ReadUInt32 (file.MaxOffset-8);
    int count = file.View.ReadInt32 (file.MaxOffset-4);
    if (!IsSaneCount (count) || index_offset >= file.MaxOffset)
        return null;
    uint index_size = (uint)count * 8u;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry {
            Name = string.Format ("{0}#{1:D4}", base_name, i),
            Offset = file.View.ReadUInt32 (index_offset),
            Size   = file.View.ReadUInt32 (index_offset+4),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    foreach (var entry in dir)
    {
        uint signature = file.View.ReadUInt32 (entry.Offset);
        if (0 == (signature & 0xFFFF) || 0x4D42 == (signature & 0xFFFF))
            entry.Type = "image";
        else if (AudioFormat.Wav.Signature == signature)
            entry.Type = "audio";
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Tsd/ArcMCD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
