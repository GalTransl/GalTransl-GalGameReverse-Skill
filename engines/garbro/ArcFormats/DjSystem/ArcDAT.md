# DjSystem / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/DJSYSTEM` / `GameRes.Formats.DjSystem.DatOpener` | `dat` | `46494c45` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "FILECMB-DATA-LIST-IN\n"))` |
| `DatOpener.OpenEntry` | `if (arc.File.View.AsciiEqual (entry.Offset, "DJCODE NLINE-"))` |
| `DatOpener.OpenEntry` | `if (arc.File.View.AsciiEqual (entry.Offset+13, "ENCODE\n"))` |
| `DatOpener.OpenEntry` | `else if (arc.File.View.AsciiEqual (entry.Offset+13, "NO-ENCODE\n"))` |
| `DatOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset+23, entry.Size-23);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DjSystem.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Regex IndexEntryRe = new Regex (@"^(\S+)\t(\d+)\s*\t(\d+)") ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "FILECMB-DATA-LIST-IN\n"))
        return null;
    using (var input = file.CreateStream())
    using (var index = new StreamReader (input, Encodings.cp932))
    {
        var dir = new List<Entry>();
        index.ReadLine();
        for (;;)
        {
            var line = index.ReadLine();
            if (null == line || "LIST-END" == line)
                break;
            var match = IndexEntryRe.Match (line);
            if (!match.Success)
                return null;
            var name   = match.Groups[1].Value;
            uint start = UInt32.Parse (match.Groups[2].Value);
            uint end   = UInt32.Parse (match.Groups[3].Value);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = start;
            entry.Size   = end - start;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            if (name.HasExtension (".vic"))
                entry.Type = "audio";
            dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (arc.File.View.AsciiEqual (entry.Offset, "DJCODE NLINE-"))
    {
        if (arc.File.View.AsciiEqual (entry.Offset+13, "ENCODE\n"))
        {
            var input = arc.File.CreateStream (entry.Offset+20, entry.Size-20);
            return new XoredStream (input, 0xFF);
        }
        else if (arc.File.View.AsciiEqual (entry.Offset+13, "NO-ENCODE\n"))
        {
            var data = arc.File.View.ReadBytes (entry.Offset+23, entry.Size-23);
            for (int i = 0; i < data.Length; ++i)
            {
                if (data[i] == '\r' && i+1 < data.Length && data[i+1] == '\n')
                    ++i;
                else
                    data[i] ^= 0xFF;
            }
            return new BinMemoryStream (data, entry.Name);
        }
    }
    return base.OpenEntry (arc, entry);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/DjSystem/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
