# FrontierWorks / ArcPCARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCARC` / `GameRes.Formats.FrontierWorks.PcArcOpener` | `pcarc` | `30313030` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PcArcOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "0100"))` |
| `PcArcOpener.TryOpen` | `var dir_count = file.View.ReadInt32 (4);` |
| `PcArcOpener.TryOpen` | `var data_offset = file.View.ReadInt64 (8);` |
| `PcArcOpener.TryOpen` | `var dir_offset = file.View.ReadInt64 (offset);` |
| `PcArcOpener.TryOpen` | `var path = file.View.ReadString (dir_offset, 0x40);` |
| `PcArcOpener.TryOpen` | `var entry_count = file.View.ReadInt32 (dir_offset+0x40);` |
| `PcArcOpener.TryOpen` | `entry.Name = path+file.View.ReadString (dir_offset, 0x40);` |
| `PcArcOpener.TryOpen` | `entry.Offset = data_offset+file.View.ReadInt64 (dir_offset+0x40);` |
| `PcArcOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (dir_offset+0x48);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FrontierWorks.PcArcOpener

继承/接口：`ArchiveFormat`。

#### PcArcOpener

```csharp
public PcArcOpener() {
    Extensions = new string[] { "pcarc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "0100"))
        return null;
    var dir_count = file.View.ReadInt32 (4);
    if (dir_count <= 0 || dir_count > 32)
        return null;
    var data_offset = file.View.ReadInt64 (8);
    if (data_offset < 0x190)
        return null;
    var offset = 0x10;
    var dir = new List<Entry> ();
    for (var i = 0; i < dir_count; i++)
    {
        var dir_offset = file.View.ReadInt64 (offset);
        offset += 8;
        if (dir_offset < 0x190)
            break;
        var path = file.View.ReadString (dir_offset, 0x40);
        var entry_count = file.View.ReadInt32 (dir_offset+0x40);
        dir_offset += 0x50;
        if (!string.IsNullOrEmpty (path) && !path.EndsWith ("/"))
            path += "/";
        for (var j = 0; j < entry_count; j++)
        {
            var entry = new Entry ();
            entry.Name = path+file.View.ReadString (dir_offset, 0x40);
            entry.Offset = data_offset+file.View.ReadInt64 (dir_offset+0x40);
            entry.Size = file.View.ReadUInt32 (dir_offset+0x48);
            dir.Add (entry);
            dir_offset += 0x50;
        }
    }
    DetectFileTypes (dir);
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Name.HasExtension (".gz"))
    {
        using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
        using (var gzs = new GZipStream (input, CompressionMode.Decompress))
        {
            var output = new MemoryStream ();
            gzs.CopyTo (output);
            return new BinMemoryStream (output, entry.Name.Substring (0, entry.Name.Length-3));
        }
    }
    return base.OpenEntry (arc, entry);
}
```

#### DetectFileTypes

```csharp
static void DetectFileTypes (List<Entry> dir) {
    foreach (var entry in dir)
    {
        var name = entry.Name;
        if (name.HasExtension (".gz"))
            name = name.Substring (0, name.Length-3);
        if (name.HasExtension (".oggl"))
            entry.Type = "audio";
        if (string.IsNullOrEmpty (entry.Type))
            entry.Type = FormatCatalog.Instance.GetTypeFromName (name);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/FrontierWorks/ArcPCARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
