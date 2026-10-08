# SoftwareHouseParsley / ArcCG3：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CG/DESERT` / `GameRes.Formats.Parsley.DesertCgOpener` | `` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DesertCgOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `DesertCgOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_pos);` |
| `DesertCgOpener.LookupFileNameTable` | `var name = src.View.ReadString (offset, 0x104);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Parsley.DesertCgOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal static Dictionary<string, uint> FileNameTableMap = new Dictionary<string, uint> {
    { @"..\DTime.exe", 0x49E348 },
}
```

#### DesertCgOpener

```csharp
public DesertCgOpener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!VFS.IsPathEqualsToFileName (file.Name, "CG"))
        return null;
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint index_pos = 4;
    var filename_table = LookupFileNameTable (file, count);
    Func<int, string> get_entry_name;
    if (filename_table != null)
        get_entry_name = n => filename_table[n];
    else
        get_entry_name = n => string.Format ("CG#{0:D4}");
    long last_offset = count * 4 + 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++ i)
    {
        uint offset = file.View.ReadUInt32 (index_pos);
        if (0 == offset)
            break;
        if (offset <= last_offset || offset >= file.MaxOffset)
            return null;
        var entry = new Entry {
            Name = get_entry_name (i),
            Type = "image",
            Offset = offset,
        };
        dir.Add (entry);
        last_offset = offset;
        index_pos += 4;
    }
    if (0 == dir.Count)
        return null;
    last_offset = file.MaxOffset;
    for (int i = dir.Count-1; i >= 0; --i)
    {
        dir[i].Size = (uint)(last_offset - dir[i].Offset);
        last_offset = dir[i].Offset;
    }
    return new ArcFile (file, this, dir);
}
```

#### LookupFileNameTable

```csharp
List<string> LookupFileNameTable (ArcView file, int count) {
    try
    {
        var dir_name = Path.GetDirectoryName (file.Name);
        foreach (var source in FileNameTableMap.Keys)
        {
            var src_name = Path.Combine (dir_name, source);
            if (File.Exists (src_name))
            {
                using (var src = new ArcView (src_name))
                {
                    var exe = new ExeFile (src);
                    long offset = exe.GetAddressOffset (FileNameTableMap[source]);
                    if (offset >= src.MaxOffset || offset + 0x104 * count > src.MaxOffset)
                        return null;
                    var dir = new List<string> (count);
                    for (int i = 0; i < count; ++i)
                    {
                        var name = src.View.ReadString (offset, 0x104);
                        dir.Add (name);
                        offset += 0x104;
                    }
                    return dir;
                }
            }
        }
    }
    catch { }
    return null;
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/SoftwareHouseParsley/ArcCG3.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
