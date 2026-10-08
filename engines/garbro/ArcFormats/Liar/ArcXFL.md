# Liar / ArcXFL：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `XFL` / `GameRes.Formats.Liar.XflOpener` | `xfl` | `4c420100` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `XflOpener.ReadDirectory` | `uint dir_size = file.View.ReadUInt32 (base_offset+4);` |
| `XflOpener.ReadDirectory` | `int count     = file.View.ReadInt32 (base_offset+8);` |
| `XflOpener.ReadDirectory` | `string name = file.View.ReadString (cur_offset, 32);` |
| `XflOpener.ReadDirectory` | `var entry_offset = data_offset + file.View.ReadUInt32 (cur_offset+32);` |
| `XflOpener.ReadDirectory` | `var entry_size   = file.View.ReadUInt32 (cur_offset+36);` |
| `XflOpener.ReadDirectory` | `if (name.HasExtension (".xfl") && file.View.ReadUInt32 (entry_offset) == Signature)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Liar.XflOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var dir = ReadDirectory (file, 0, file.MaxOffset, "");
    if (dir != null)
        return new ArcFile (file, this, dir);
    else
        return null;
}
```

#### ReadDirectory

```csharp
internal List<Entry> ReadDirectory (ArcView file, long base_offset, long max_offset, string base_dir) {
    uint dir_size = file.View.ReadUInt32 (base_offset+4);
    int count     = file.View.ReadInt32 (base_offset+8);
    if (!IsSaneCount (count))
        return null;
    long data_offset = base_offset + dir_size + 12;
    if (dir_size >= max_offset || data_offset >= max_offset)
        return null;

    file.View.Reserve (base_offset, (uint)(data_offset - base_offset));
    long cur_offset = base_offset + 12;

    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        if (cur_offset+40 > data_offset)
            return null;
        string name = file.View.ReadString (cur_offset, 32);
        var entry_offset = data_offset + file.View.ReadUInt32 (cur_offset+32);
        var entry_size   = file.View.ReadUInt32 (cur_offset+36);
        List<Entry> subdir = null;
        name = VFS.CombinePath (base_dir, name);
        if (name.HasExtension (".xfl") && file.View.ReadUInt32 (entry_offset) == Signature)
        {
            subdir = ReadDirectory (file, entry_offset, entry_offset + entry_size, name);
        }
        if (subdir != null && subdir.Count > 0)
        {
            dir.AddRange (subdir);
        }
        else
        {

            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = entry_offset;
            entry.Size = entry_size;
            if (!entry.CheckPlacement (max_offset))
                return null;
            dir.Add (entry);
        }
        cur_offset += 40;
    }
    return dir;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Liar/ArcXFL.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
