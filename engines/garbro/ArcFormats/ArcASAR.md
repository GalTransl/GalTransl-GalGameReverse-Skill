# ArcFormats / ArcASAR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ASAR` / `GameRes.Formats.Chromium.AsarOpener` | `asar` | `04000000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AsarOpener.TryOpen` | `if (file.View.ReadUInt32 (4) != file.View.ReadUInt32 (8) + 4)` |
| `AsarOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0x0C);` |
| `AsarOpener.TryOpen` | `string json = file.View.ReadString (0x10, index_size, Encoding.UTF8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Chromium.AsarNode

#### JsonProperty

```csharp
[JsonProperty("files")]
public Dictionary<string, AsarNode> Files { get; set; }
```

#### JsonProperty

```csharp
[JsonProperty("size")]
public uint Size { get; set; }
```

#### JsonProperty

```csharp
[JsonProperty("offset")]
public string Offset { get; set; }
```

#### JsonProperty

```csharp
[JsonProperty("unpacked")]
public bool Unpacked { get; set; }
```

#### JsonProperty

```csharp
[JsonProperty("link")]
public string Link { get; set; }
```

### GameRes.Formats.Chromium.AsarOpener

继承/接口：`ArchiveFormat`。

#### AsarOpener

```csharp
public AsarOpener () {
    Extensions = new string[] { "asar" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.MaxOffset < 0x10)
        return null;
    if (file.View.ReadUInt32 (4) != file.View.ReadUInt32 (8) + 4)
        return null;
    uint index_size = file.View.ReadUInt32 (0x0C);
    if (index_size > file.MaxOffset - 0x10)
        return null;
    string json = file.View.ReadString (0x10, index_size, Encoding.UTF8);
    AsarNode dict;
    try
    {
        dict = JsonConvert.DeserializeObject<AsarNode> (json);
    }
    catch (JsonException)
    {
        return null;
    }
    if (null == dict)
        return null;
    var dir = new List<Entry> ();
    long pad = (0x10L + index_size + 3) & ~3L;
    ParseIndex (dir, dict, pad);
    dir.RemoveAll (e => e.Size != 0 && !e.CheckPlacement (file.MaxOffset));
    return new ArcFile (file, this, dir);
}
```

#### ParseIndex

```csharp
void ParseIndex (List<Entry> dir, AsarNode dict, long pad, string cur = "") {
    if (dict.Files != null)
    {
        foreach (var kv in dict.Files)
        {
            string k = kv.Key;
            AsarNode v = kv.Value;
            ParseIndex (dir, v, pad, cur != "" ? $"{cur}/{k}" : k);
        }
    }
    else
    {
        if (dict.Unpacked || !string.IsNullOrEmpty (dict.Link) || string.IsNullOrEmpty (dict.Offset))
            return;
        long offset;
        if (!long.TryParse (dict.Offset, out offset))
            return;
        var entry = new Entry {
            Name = cur,
            Size = dict.Size,
            Offset = offset + pad,
            Type = FormatCatalog.Instance.GetTypeFromName (cur)
        };
        dir.Add (entry);
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ArcASAR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
