# AdvSys / ArcAdvSys3：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/ADVSYS3` / `GameRes.Formats.AdvSys.ArcOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `uint size = file.View.ReadUInt32 (current_offset);` |
| `ArcOpener.TryOpen` | `uint name_length = file.View.ReadUInt16 (current_offset+8);` |
| `ArcOpener.TryOpen` | `var name = file.View.ReadString (current_offset+10, name_length);` |
| `ArcOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (current_offset);` |
| `ArcOpener.TryOpen` | `if (file.View.AsciiEqual (current_offset+4, "GWD"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AdvSys.ArcOpener

继承/接口：`ArchiveFormat`。

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat")
        || !Path.GetFileName (file.Name).StartsWith ("arc", StringComparison.InvariantCultureIgnoreCase))
        return null;
    long current_offset = 0;
    var dir = new List<Entry>();
    while (current_offset < file.MaxOffset)
    {
        uint size = file.View.ReadUInt32 (current_offset);
        if (0 == size)
            break;
        uint name_length = file.View.ReadUInt16 (current_offset+8);
        if (0 == name_length || name_length > 0x100)
            return null;
        var name = file.View.ReadString (current_offset+10, name_length);
        if (0 == name.Length)
            return null;
        current_offset += 10 + name_length;
        if (current_offset + size > file.MaxOffset)
            return null;
        var entry = new Entry {
            Name = name,
            Offset = current_offset,
            Size = size,
        };
        uint signature = file.View.ReadUInt32 (current_offset);
        if (file.View.AsciiEqual (current_offset+4, "GWD"))
        {
            entry.Type = "image";
            entry.Name = Path.ChangeExtension (entry.Name, "gwd");
        }
        else
        {
            var res = AutoEntry.DetectFileType (signature);
            entry.ChangeType (res);
        }
        dir.Add (entry);
        current_offset += size;
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/AdvSys/ArcAdvSys3.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
