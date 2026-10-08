# Dvn / ArcDVN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DVN` / `GameRes.Formats.Dvn.DvnOpener` | `dvn` | `44564e42` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DvnOpener.TryOpen` | `uint version = file.View.ReadUInt32 (4);` |
| `DvnOpener.TryOpen` | `uint name_length = file.View.ReadUInt32 (offset);` |
| `DvnOpener.TryOpen` | `var name = file.View.ReadString (offset + 4, name_length);` |
| `DvnOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Dvn.DvnOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly string[] ResourceLists = new[] {
    "resources/main.json",
    "game/backgrounds.json",
    "game/characters.json",
    "game/animations.json"
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint version = file.View.ReadUInt32 (4);
    if (version != 1)
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name).ToLowerInvariant();

    var resmap = new Dictionary<string, Resource> ();
    foreach (var list in ResourceLists)
    {
        try
        {
            using (var input = VFS.OpenStream (list))
            using (var reader = new StreamReader (input))
            using (var jtr = new JsonTextReader (reader))
            {
                var serializer = new JsonSerializer();
                var json = serializer.Deserialize<Dictionary<string, Resource>> (jtr);
                resmap = resmap.Concat (json).ToDictionary (x => x.Key, x => x.Value);
            }
        }
        catch
        {
            continue;
        }
    }

    var dir = new List<Entry> ();
    uint offset = 8;
    while (offset < file.MaxOffset)
    {
        uint name_length = file.View.ReadUInt32 (offset);
        var name = file.View.ReadString (offset + 4, name_length);
        if (resmap.ContainsKey (name))
            name = resmap[name].Path;
        offset += name_length + 4;
        var entry = Create<Entry> (name);
        entry.Size = file.View.ReadUInt32 (offset);
        entry.Offset = offset + 4;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if ("images" == base_name)
            entry.Type = "image";
        dir.Add (entry);
        offset += entry.Size + 4;
    }

    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Dvn/ArcDVN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
