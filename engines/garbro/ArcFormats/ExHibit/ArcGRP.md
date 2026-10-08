# ExHibit / ArcGRP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GRP/EXHIBIT` / `GameRes.Formats.ExHibit.GrpOpener` | `grp` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GrpOpener.TryOpen` | `if (!match.Success \|\| file.View.AsciiEqual (0, "AiFS"))` |
| `GrpOpener.TryOpen` | `if (toc_file.View.AsciiEqual (0, "AiFS"))` |
| `GrpOpener.TryOpen` | `int res_count = toc_file.View.ReadInt32 (0xC);` |
| `GrpOpener.TryOpen` | `int num = toc_file.View.ReadInt32 (index_offset);` |
| `GrpOpener.TryOpen` | `num = toc_file.View.ReadInt32 (index_offset);` |
| `GrpOpener.TryOpen` | `uint entries = toc_file.View.ReadUInt32 (index_offset+0xC);` |
| `GrpOpener.TryOpen` | `int count = toc_file.View.ReadInt32 (index_offset+0xC);` |
| `GrpOpener.TryOpen` | `int start_index = toc_file.View.ReadInt32 (index_offset+4);` |
| `GrpOpener.TryOpen` | `uint size   = toc_file.View.ReadUInt32 (index_offset+4);` |
| `GrpOpener.TryOpen` | `Offset = toc_file.View.ReadUInt32 (index_offset),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ExHibit.GrpOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Regex s_ResNameRe = new Regex (@"res(\d+)\.grp$", RegexOptions.IgnoreCase) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var match = s_ResNameRe.Match (file.Name);
    if (!match.Success || file.View.AsciiEqual (0, "AiFS"))
        return null;

    var digits = match.Groups[1];
    int arc_num = UInt16.Parse (digits.Value);
    int toc_num = arc_num - 1;
    int arc_index = 1;

    ArcView toc_file = null;
    var toc_name_sb = new StringBuilder (file.Name.Length);
    while (toc_num >= 0)
    {
        toc_name_sb.Clear();
        toc_name_sb.Append (file.Name);
        toc_name_sb.Remove (digits.Index, digits.Length);
        toc_name_sb.Insert (digits.Index, toc_num.ToString ("D4"));
        var toc_name = toc_name_sb.ToString();
        if (!VFS.FileExists (toc_name))
            return null;
        toc_file = VFS.OpenView (toc_name);
        if (toc_file.View.AsciiEqual (0, "AiFS"))
            break;
        toc_file.Dispose();
        toc_file = null;
        toc_num--;
        arc_index++;
    }
    if (null == toc_file)
        return null;
    using (toc_file)
    {
        int res_count = toc_file.View.ReadInt32 (0xC);
        if (res_count < arc_index)
            return null;
        uint index_offset = 0x10;

        bool arc_found = false;
        for (int i = 0; i < res_count && index_offset < toc_file.MaxOffset; ++i)
        {
            int num = toc_file.View.ReadInt32 (index_offset);
            if (0x01000000 == num)
            {
                index_offset += 4;
                num = toc_file.View.ReadInt32 (index_offset);
            }
            if (num == arc_index)
            {
                arc_found = true;
                break;
            }
            uint entries = toc_file.View.ReadUInt32 (index_offset+0xC);
            index_offset += 0x10 + entries * 8;
        }
        if (!arc_found)
            return null;
        int count = toc_file.View.ReadInt32 (index_offset+0xC);
        if (!IsSaneCount (count))
            return null;
        int start_index = toc_file.View.ReadInt32 (index_offset+4);
        index_offset += 0x10;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            uint size   = toc_file.View.ReadUInt32 (index_offset+4);
            if (size != 0)
            {
                var entry = new Entry {
                    Name = string.Format ("{0:D5}.ogg", start_index+i),
                    Type = "audio",
                    Offset = toc_file.View.ReadUInt32 (index_offset),
                    Size = size,
                };
                if (!entry.CheckPlacement (file.MaxOffset))
                    return null;
                dir.Add (entry);
            }
            index_offset += 8;
        }
        if (0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ExHibit/ArcGRP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
