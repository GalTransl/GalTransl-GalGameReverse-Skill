# BlackRainbow / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/BR` / `GameRes.Formats.BlackRainbow.DatOpener` | `dat`, `pak` | `02000000`, `04000000`, `05000000`, `06000000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `DatOpener.TryOpen` | `uint base_offset = file.View.ReadUInt32 (0x0c);` |
| `DatOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `DatOpener.TryOpen` | `string name = file.View.ReadString (offset, 0x24);` |
| `DatOpener.TryOpen` | `if (file.View.AsciiEqual (offset + 0x24, "_BMD"))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BlackRainbow.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat", "pak" };
    Signatures = new uint[] { 2u, 4u, 5u, 6u };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint base_offset = file.View.ReadUInt32 (0x0c);
    uint index_offset = 0x10;
    uint index_size = 4u * (uint)count;
    if (base_offset >= file.MaxOffset || base_offset < (index_offset+index_size))
        return null;
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    var index = new List<uint> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        if (offset != 0xffffffff)
            index.Add (base_offset + offset);
        index_offset += 4;
    }
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    index.Sort();
    var dir = new List<Entry> (index.Count);
    for (int i = 0; i < index.Count; ++i)
    {
        long offset = index[i];
        string name = file.View.ReadString (offset, 0x24);
        if (0 == name.Length)
        {
            name = string.Format ("{0:D2}_{1}#{0:D2}", i, base_name);
            if (file.View.AsciiEqual (offset + 0x24, "_BMD"))
                name += ".bmd";
        }
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset + 0x24;
        entry.Size   = (uint)((i + 1 < index.Count ? index[i+1]  : file.MaxOffset) - entry.Offset);
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/BlackRainbow/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
