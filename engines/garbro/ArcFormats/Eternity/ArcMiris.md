# Eternity / ArcMiris：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/MIRIS` / `GameRes.Formats.Miris.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Miris.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Regex IndexEntryRe = new Regex (@"\G([^,]+),(\d+),(\d+)#") ;
```

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var base_dir = VFS.GetDirectoryName (file.Name);
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var list_file = VFS.CombinePath (base_dir, base_name+"l.dat");
    if (!VFS.FileExists (list_file))
        return null;
    string index;
    using (var ls = VFS.OpenStream (list_file))
    using (var zls = new ZLibStream (ls, CompressionMode.Decompress))
    using (var reader = new StreamReader (zls, Encodings.cp932))
    {
        index = reader.ReadToEnd();
    }
    if (string.IsNullOrEmpty (index))
        return null;

    var dir = new List<Entry>();
    var match = IndexEntryRe.Match (index);
    while (match.Success)
    {
        var entry = new Entry {
            Name    = match.Groups[1].Value,
            Offset  = UInt32.Parse (match.Groups[3].Value),
            Size    = UInt32.Parse (match.Groups[2].Value),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        match = match.NextMatch();
    }
    if (0 == dir.Count)
        return null;
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Eternity/ArcMiris.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
