# Groover / ArcPCG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/PCG` / `GameRes.Formats.Groover.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int parts_count = index.View.ReadInt32 (0);` |
| `DatOpener.TryOpen` | `int count = index.View.ReadInt32 (4);` |
| `DatOpener.TryOpen` | `var name = index.View.ReadString (name_pos, 0x20);` |
| `DatOpener.TryOpen` | `first_index = index.View.ReadInt32 (first_index_pos);` |
| `DatOpener.TryOpen` | `last_index = index.View.ReadInt32 (last_index_pos);` |
| `DatOpener.TryOpen` | `var name = index.View.ReadString (index_offset, name_size);` |
| `DatOpener.TryOpen` | `entry.Size = index.View.ReadUInt32 (index_offset+name_size);` |
| `DatOpener.TryOpen` | `entry.Offset = index.View.ReadUInt32 (index_offset+name_size+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Groover.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Regex IndexNameRe = new Regex (@"^((.+)0\d)\.dat$", RegexOptions.IgnoreCase) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    var arc_name = Path.GetFileName (file.Name);
    var match = IndexNameRe.Match (arc_name);
    if (!match.Success)
        return null;
    var base_name = match.Groups[2].Value;
    base_name = VFS.ChangeFileName (file.Name, base_name);
    var index_name = base_name + ".pcg";
    if (!VFS.FileExists (index_name))
    {
        index_name = base_name + ".spf";
        if (!VFS.FileExists (index_name))
            return null;
    }
    arc_name = match.Groups[1].Value;
    using (var index = VFS.OpenView (index_name))
    {
        int parts_count = index.View.ReadInt32 (0);
        int count = index.View.ReadInt32 (4);
        if (parts_count > 10 || !IsSaneCount (count))
            return null;
        int entry_size = (int)(index.MaxOffset - 0x198) / count;
        if (entry_size < 0x30)
            return null;
        int first_index = -1, last_index = -1;
        for (int i = 0; i < parts_count; ++i)
        {
            int name_pos = 8 + i * 0x20;
            var name = index.View.ReadString (name_pos, 0x20);
            if (name == arc_name)
            {
                int first_index_pos = 0x148 + i * 4;
                int last_index_pos = 0x170 + i * 4;
                first_index = index.View.ReadInt32 (first_index_pos);
                last_index = index.View.ReadInt32 (last_index_pos);
                break;
            }
        }
        if (first_index < 0 || first_index >= last_index || last_index > count)
            return null;

        uint name_size = entry_size >= 0x48 ? 0x40u : 0x20u;
        int index_offset = 0x198 + entry_size * first_index;
        var dir = new List<Entry> (last_index-first_index);
        for (int i = first_index; i < last_index; ++i)
        {
            var name = index.View.ReadString (index_offset, name_size);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Size = index.View.ReadUInt32 (index_offset+name_size);
            entry.Offset = index.View.ReadUInt32 (index_offset+name_size+4);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            index_offset += entry_size;
        }
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Groover/ArcPCG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
