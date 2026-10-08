# Will / ArcWIP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `WIP/MULTI` / `GameRes.Formats.Will.WipOpener` | `wip` | `57495046` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `WipOpener.TryOpen` | `int count = file.View.ReadInt16 (4);` |
| `WipOpener.TryOpen` | `var wipf_header = file.View.ReadBytes (0, 0x20);` |
| `WipOpener.TryOpen` | `int bpp = LittleEndian.ToInt16 (wipf_header, 6);` |
| `WipOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset+0x14);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Will.WipfEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public override string Type { get { return "image"; } }

public byte[]   Header ;
```

### GameRes.Formats.Will.WipOpener

继承/接口：`ArchiveFormat`。

#### WipOpener

```csharp
public WipOpener () {
    Extensions = new string[] { "wip" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt16 (4);
    if (!IsSaneCount (count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var wipf_header = file.View.ReadBytes (0, 0x20);
    int bpp = LittleEndian.ToInt16 (wipf_header, 6);
    LittleEndian.Pack ((short)1, wipf_header, 4);
    int index_offset = 8;
    long entry_offset = 8 + 0x18 * count;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new WipfEntry { Name = string.Format ("{0}#{1:D4}.wip", base_name, i) };
        entry.Size = file.View.ReadUInt32 (index_offset+0x14);
        entry.Offset = entry_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Header = wipf_header.Clone() as byte[];
        file.View.Read (index_offset, entry.Header, 8, 0x18);
        if (8 == bpp)
            entry.Size += 0x400;
        entry.IsPacked = true;
        entry.UnpackedSize = entry.Size + (uint)entry.Header.Length;
        dir.Add (entry);
        index_offset += 0x18;
        entry_offset += entry.Size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var went = (WipfEntry)entry;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new PrefixStream (went.Header, input);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Will/ArcWIP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
