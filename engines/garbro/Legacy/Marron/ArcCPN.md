# Marron / ArcCPN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/CPN` / `GameRes.Formats.Marron.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `key = cpn.View.ReadByte (0);` |
| `DatOpener.TryOpen` | `var cpn_data = cpn.View.ReadBytes (1, (uint)(cpn.MaxOffset - 1));` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Marron.CpnArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte Key ;
```

#### CpnArchive

```csharp
public CpnArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Marron.DatOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Regex CpnEntryRe = new Regex (@"#(?:\./)?(?<name>[^$]+)\$(?<offset>\d+)\*(?<size>\d+)\+") ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    var cpn_name = Path.ChangeExtension (file.Name, ".cpn");
    if (!VFS.FileExists (cpn_name))
        return null;
    byte key;
    string cpn_index;
    using (var cpn = VFS.OpenView (cpn_name))
    {
        key = cpn.View.ReadByte (0);
        var cpn_data = cpn.View.ReadBytes (1, (uint)(cpn.MaxOffset - 1));
        for (int i = 0; i < cpn_data.Length; ++i)
            cpn_data[i] ^= key;
        cpn_index = Encodings.cp932.GetString (cpn_data);
    }
    int idx = cpn_index.IndexOf ('#', 1);
    if (idx <= 1)
        return null;
    var data_name = cpn_index.Substring (1, idx-1);
    if (!VFS.IsPathEqualsToFileName (file.Name, data_name))
        return null;
    var dir = new List<Entry>();
    var match = CpnEntryRe.Match (cpn_index, idx);
    while (match.Success)
    {
        var name = match.Groups["name"].Value;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = UInt32.Parse (match.Groups["offset"].Value);
        entry.Size   = UInt32.Parse (match.Groups["size"].Value);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        match = match.NextMatch();
    }
    if (0 == dir.Count)
        return null;
    return new CpnArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var carc = arc as CpnArchive;
    if (null == carc)
        return input;
    return new XoredStream (input, carc.Key);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../../ArcFormats/CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Marron/ArcCPN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
