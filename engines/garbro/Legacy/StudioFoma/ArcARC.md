# StudioFoma / ArcARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/FOMA` / `GameRes.Formats.Foma.ArcOpener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.GetEntryList` | `uint name_addr = exe.View.ReadUInt32 (table_offset);` |
| `ArcOpener.GetEntryList` | `entry.Offset = exe.View.ReadUInt32 (table_offset + 4);` |
| `ArcOpener.GetEntryList` | `entry.Size   = exe.View.ReadUInt32 (table_offset + 8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Foma.ArcOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
HashSet<string> m_known_arc_names = null ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc_name = Path.GetFileName (file.Name).ToUpperInvariant();
    if (!KnownArcNames.Contains (arc_name))
        return null;
    var dir_name = VFS.GetDirectoryName (file.Name);
    foreach (var scheme in KnownSchemes)
    {
        var exe_name = VFS.CombinePath (dir_name, scheme.Key);
        if (VFS.FileExists (exe_name))
        {
            uint table_offset;
            if (scheme.Value.TryGetValue (arc_name, out table_offset))
            {
                var dir = GetEntryList (exe_name, table_offset, file.MaxOffset);
                if (dir != null)
                    return new ArcFile (file, this, dir);
            }
        }
    }
    return null;
}
```

#### GetEntryList

```csharp
internal List<Entry> GetEntryList (string exe_name, long table_offset, long max_offset) {
    using (var exe_file = VFS.OpenView (exe_name))
    {
        if (table_offset >= exe_file.MaxOffset)
            return null;
        var exe = new ExeFile (exe_file);
        var dir = new List<Entry>();
        while (table_offset+12 <= exe_file.MaxOffset)
        {
            uint name_addr = exe.View.ReadUInt32 (table_offset);
            if (0 == name_addr)
                break;
            var name = exe.GetCString (name_addr);
            if (string.IsNullOrEmpty (name))
                return null;
            var entry = Create<Entry> (name);
            entry.Offset = exe.View.ReadUInt32 (table_offset + 4);
            entry.Size   = exe.View.ReadUInt32 (table_offset + 8);
            if (!entry.CheckPlacement (max_offset))
                return null;
            dir.Add (entry);
            table_offset += 12;
        }
        return dir;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../../ArcFormats/ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/StudioFoma/ArcARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
