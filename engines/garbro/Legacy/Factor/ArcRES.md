# Factor / ArcRES：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PACK/FACTOR` / `GameRes.Formats.Factor.PackOpener` | `` | 无固定签名或来源表达式未解析 | `False` |

该入口只在来源 Debug 配置注册，不能当作 Release 工具的可用格式保证。

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PackOpener.TryOpen` | `uint size = file.View.ReadUInt32 (offset);` |
| `PackOpener.ReadNames` | `uint offset = 4 + pack.View.ReadUInt32 (0);` |
| `PackOpener.ReadNames` | `offset += 4 + pack.View.ReadUInt32 (offset);` |
| `PackOpener.ReadNames` | `uint size = pack.View.ReadUInt32 (offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Factor.PackOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Regex PackNameRe = new Regex (@"^pack(\d)$") ;

static readonly Regex FirstLineRe = new Regex (@"\\(\d)\\$") ;
```

#### PackOpener

```csharp
public PackOpener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var match = PackNameRe.Match (base_name);
    if (!match.Success)
        return null;
    var pack_ext = Path.GetExtension (file.Name);
    List<string> names = new List<string>();

    var dir = new List<Entry>();
    long offset = 0;
    int i = 0;
    while (offset < file.MaxOffset)
    {
        uint size = file.View.ReadUInt32 (offset);
        offset += 4;
        string name;
        if (i < names.Count)
            name = names[i];
        else
            name = string.Format ("{0}#{1:D4}{2}", base_name, i, pack_ext);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        entry.Size   = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        ++i;
        offset += size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (entry.Name.HasExtension (".res"))
        input = new XoredStream (input, 0x80);
    return input;
}
```

#### ReadNames

```csharp
IEnumerable<string> ReadNames (string res_name, string num) {
    if (!VFS.FileExists (res_name))
        yield break;
    using (var pack = VFS.OpenView (res_name))
    {
        uint offset = 4 + pack.View.ReadUInt32 (0);
        offset += 4 + pack.View.ReadUInt32 (offset);
        uint size = pack.View.ReadUInt32 (offset);
        offset += 4;
        if (offset >= pack.MaxOffset)
            yield break;
        using (var res = pack.CreateStream (offset, size))
        using (var decrypted = new XoredStream (res, 0x80))
        using (var input = new StreamReader (decrypted, Encodings.cp932))
        {
            var line = input.ReadLine();
            if (string.IsNullOrEmpty (line))
                yield break;
            var match = FirstLineRe.Match (line);
            if (!match.Success || match.Groups[1].Value != num)
                yield break;
            while ((line = input.ReadLine()) != null)
            {
                yield return line;
            }
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../../ArcFormats/CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Factor/ArcRES.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
