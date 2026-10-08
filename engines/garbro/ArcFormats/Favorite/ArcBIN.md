# Favorite / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/FVP` / `GameRes.Formats.FVP.Bin2Opener` | `bin` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Bin2Opener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `Bin2Opener.TryOpen` | `uint name_index_size = file.View.ReadUInt32 (4);` |
| `Bin2Opener.TryOpen` | `uint filename_offset = file.View.ReadUInt32 (index_offset);` |
| `Bin2Opener.TryOpen` | `var name = file.View.ReadString (names_base+filename_offset, name_index_size-filename_offset);` |
| `Bin2Opener.TryOpen` | `Offset  = file.View.ReadUInt32 (index_offset+4),` |
| `Bin2Opener.TryOpen` | `Size    = file.View.ReadUInt32 (index_offset+8),` |
| `Bin2Opener.TryOpen` | `var signature = file.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FVP.Bin2Opener

继承/接口：`ArchiveFormat`。

#### Bin2Opener

```csharp
public Bin2Opener () {
    Extensions = new string[] { "bin" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint index_size = (uint)count * 12;
    uint name_index_size = file.View.ReadUInt32 (4);
    if (8L + index_size + name_index_size >= file.MaxOffset)
        return null;

    uint index_offset = 8;
    file.View.Reserve (index_offset, index_size + name_index_size);
    uint names_base = index_offset + index_size;
    var dir = new List<Entry> (count);
    string entry_type = null;
    string arc_name = Path.GetFileNameWithoutExtension (file.Name).ToLowerInvariant();
    if ("voice" == arc_name || "bgm" == arc_name)
        entry_type = "audio";
    for (int i = 0; i < count; ++i)
    {
        uint filename_offset = file.View.ReadUInt32 (index_offset);
        if (filename_offset >= name_index_size)
            return null;
        var name = file.View.ReadString (names_base+filename_offset, name_index_size-filename_offset);
        if (0 == name.Length)
            return null;
        var entry = new Entry {
            Name    = name,
            Offset  = file.View.ReadUInt32 (index_offset+4),
            Size    = file.View.ReadUInt32 (index_offset+8),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (entry_type != null)
            entry.Type = entry_type;
        dir.Add (entry);
        index_offset += 12;
    }
    if (null == entry_type)
    {
        foreach (var entry in dir)
        {
            var signature = file.View.ReadUInt32 (entry.Offset);
            if (0 == signature)
                continue;
            var res = FormatCatalog.Instance.LookupSignature (signature).FirstOrDefault();
            if (null == res)
                continue;
            entry.Type = res.Type;
            var ext = res.Extensions.FirstOrDefault();
            if (!string.IsNullOrEmpty (ext))
                entry.Name += '.'+ext;
        }
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Favorite/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
