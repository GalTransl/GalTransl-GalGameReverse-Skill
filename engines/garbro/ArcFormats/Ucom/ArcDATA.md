# Ucom / ArcDATA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DATA/UCOM` / `GameRes.Formats.Ucom.DataOpener` | `` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DataOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "PF"))` |
| `DataOpener.TryOpen` | `if (!index.View.AsciiEqual (0, "IF"))` |
| `DataOpener.TryOpen` | `int count = index.View.ReadInt16 (2);` |
| `DataOpener.TryOpen` | `var name = index.View.ReadString (index_offset, 0x10);` |
| `DataOpener.TryOpen` | `entry.Offset = index.View.ReadUInt32 (index_offset+0x10);` |
| `DataOpener.TryOpen` | `entry.Size   = index.View.ReadUInt32 (index_offset+0x14);` |
| `DataOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Ucom.DataOpener

继承/接口：`ArchiveFormat`。

#### DataOpener

```csharp
public DataOpener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "PF"))
        return null;
    var base_name = Path.GetFileName (file.Name);
    if (!base_name.Equals ("data02", StringComparison.InvariantCultureIgnoreCase))
        return null;
    var index_name = VFS.CombinePath (VFS.GetDirectoryName (file.Name), "data01");
    if (!VFS.FileExists (index_name))
        return null;
    using (var index = VFS.OpenView (index_name))
    {
        if (!index.View.AsciiEqual (0, "IF"))
            return null;
        int count = index.View.ReadInt16 (2);
        if (!IsSaneCount (count) || 4 + 0x18 * count > index.MaxOffset)
            return null;

        uint index_offset = 4;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var name = index.View.ReadString (index_offset, 0x10);
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            entry.Offset = index.View.ReadUInt32 (index_offset+0x10);
            entry.Size   = index.View.ReadUInt32 (index_offset+0x14);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            index_offset += 0x18;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    for (int i = 0; i < data.Length; ++i)
    {
        if ((i % 5) != 0)
            data[i] ^= 0x45;
    }
    return new BinMemoryStream (data, entry.Name);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Ucom/ArcDATA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
