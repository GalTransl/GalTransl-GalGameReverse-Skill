# Tail / ArcPKG：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PKG/ARCHIVE` / `GameRes.Formats.Tail.PkgOpener` | `pkg` | `504b4720` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PkgOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PkgOpener.TryOpen` | `var offset = file.View.ReadUInt32 (index_offset);` |
| `PkgOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tail.PkgOpener

继承/接口：`CafOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_offset = 8;
    string default_type = null;
    if (base_name.Equals ("cg", StringComparison.OrdinalIgnoreCase))
        default_type = "image";
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = string.Format ("{0}#{1:D4}", base_name, i);
        var offset = file.View.ReadUInt32 (index_offset);
        Entry entry;
        if (default_type != null)
            entry = new Entry { Name = name, Type = default_type, Offset = offset };
        else
            entry = AutoEntry.Create (file, offset, name);
        entry.Size = file.View.ReadUInt32 (index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/Tail/ArcCAF.cs](ArcCAF.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Tail/ArcPKG.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
