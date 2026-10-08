# Rain / ArcBIN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BIN/RAIN` / `GameRes.Formats.Rain.BinOpener` | `bin` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BinOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `BinOpener.TryOpen` | `uint num = file.View.ReadUInt32 (index_offset);` |
| `BinOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |
| `BinOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+8);` |
| `BinOpener.OpenEntry` | `if (!arc.File.View.AsciiEqual (entry.Offset, "SZDD"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Rain.BinOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Regex PackNameRe = new Regex (@"^pack(...)\.bin$", RegexOptions.IgnoreCase) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    bool is_compressed = 0 == (count & 0x80000000);
    count &= 0x7FFFFFFF;
    if (!IsSaneCount (count))
        return null;
    var match = PackNameRe.Match (Path.GetFileName (file.Name));
    if (!match.Success)
        return null;
    var ext = match.Groups[1].Value;
    uint index_size = (uint)count * 12;
    if (index_size > file.View.Reserve (4, index_size))
        return null;
    uint index_offset = 4;
    uint data_offset = 4 + index_size;
    var dir = new List<Entry> (count);
    var seen_nums = new HashSet<uint>();
    for (int i = 0; i < count; ++i)
    {
        uint num = file.View.ReadUInt32 (index_offset);
        if (num > 0xFFFFFF || !seen_nums.Add (num))
            return null;
        var name = string.Format ("{0:D5}.{1}", num, ext);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        entry.Size   = file.View.ReadUInt32 (index_offset+8);
        if (entry.Offset < data_offset || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 12;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (!arc.File.View.AsciiEqual (entry.Offset, "SZDD"))
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset+12, entry.Size-12);
    var lzss = new LzssStream (input);
    lzss.Config.FrameFill = 0x20;
    lzss.Config.FrameInitPos = 0xFF0;
    return lzss;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Rain/ArcBIN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
