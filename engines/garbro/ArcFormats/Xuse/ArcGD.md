# Xuse / ArcGD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GD/Xuse` / `GameRes.Formats.Xuse.GdOpener` | `gd` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `GdOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `GdOpener.TryOpen` | `uint offset = idx.View.ReadUInt32 (index_offset);` |
| `GdOpener.TryOpen` | `entry.Size = idx.View.ReadUInt32(index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Xuse.GdOpener

继承/接口：`ArchiveFormat`。

#### GdOpener

```csharp
public GdOpener () {
    Extensions = new string[] { "gd" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    string index_name = Path.ChangeExtension (file.Name, ".dll");
    if (index_name == file.Name || !VFS.FileExists (index_name))
        return null;
    var index_entry = VFS.FindFile (index_name);
    if (index_entry.Size < 12)
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count) || (count & 0xFFFF) == 0x5A4D)
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    using (var idx = VFS.OpenView (index_entry))
    {
        var dir = new List<Entry> (count);
        uint index_offset = 4;
        int i = 0;
        uint last_offset = 3;
        while (index_offset+8 <= idx.MaxOffset)
        {
            uint offset = idx.View.ReadUInt32 (index_offset);
            if (offset <= last_offset)
                return null;
            var name = string.Format ("{0}#{1:D5}", base_name, i++);
            var entry = AutoEntry.Create (file, offset, name);
            entry.Size = idx.View.ReadUInt32(index_offset+4);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            last_offset = offset;
            index_offset += 8;
        }
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Xuse/ArcGD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
