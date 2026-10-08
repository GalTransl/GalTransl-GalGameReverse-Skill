# Logg / ArcMBM：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MBM` / `GameRes.Formats.Logg.MbmOpener` | `mbm` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Logg.MbmOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Dictionary<uint, string> ArcSizeToFileListMap = new Dictionary<uint, string> {
    { 0x0AB0F5F4, name_list_parameter },
    { 0x0BFFD3DA, name_list_parameter },
    { 0x09809196, name_list_parameter },
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension ("MBM"))
        return null;
    var index = GetArchiveIndex (file);
    if (null == index)
        return null;
    var dir = index.Take (index.Count - 1)
        .Select (e => new Entry {
            Name = e.Value,
            Type = FormatCatalog.Instance.GetTypeFromName (e.Value),
            Offset = e.Key
        }).ToList();
    for (int i = 1; i < dir.Count; ++i)
        dir[i-1].Size = (uint)(dir[i].Offset - dir[i-1].Offset);
    dir[dir.Count-1].Size = (uint)(file.MaxOffset - dir[dir.Count-1].Offset);
    return new ArcFile (file, this, dir);
}
```

#### GetArchiveIndex

```csharp
IDictionary<uint, string> GetArchiveIndex (ArcView file) {
    string list_name;
    if (!ArcSizeToFileListMap.TryGetValue ((uint)file.MaxOffset, out list_name))
        return null;
    var file_map = ReadFileList (list_name);
    uint last_offset = file_map.Keys.Last();
    if (last_offset != file.MaxOffset)
        return null;
    return file_map;
}
```

#### ReadFileList

```csharp
static IDictionary<uint, string> ReadFileList (string list_name) {
    var file_map = new SortedDictionary<uint,string>();
    var comma = new char[] {','};
    FormatCatalog.Instance.ReadFileList (list_name, line => {
        var parts = line.Split (comma, 2);
        uint offset = uint.Parse (parts[0], NumberStyles.HexNumber);
        if (2 == parts.Length)
        {
            file_map[offset] = parts[1];
        }
        else
        {
            file_map[offset] = null;
        }
    });
    return file_map;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Logg/ArcMBM.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
