# ArcFormats / ArcPACKDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PACKDAT` / `GameRes.Formats.SystemEpsylon.PakOpener` | `pak`, `dat` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "DAT."))` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `PakOpener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x20);` |
| `PakOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x20);` |
| `PakOpener.TryOpen` | `entry.Flags  = file.View.ReadUInt32 (index_offset+0x24);` |
| `PakOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x28);` |
| `PakOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x2c);` |
| `PakOpener.OpenEntry` | `var input = arc.File.View.ReadBytes (entry.Offset, pentry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.SystemEpsylon.PackDatEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint Flags ;
```

### GameRes.Formats.SystemEpsylon.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak", "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "DAT."))
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint index_size = 0x30 * (uint)count;
    if (index_size > file.View.Reserve (0x10, index_size))
        return null;
    var dir = new List<Entry> (count);
    long index_offset = 0x10;
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x20);
        var entry = FormatCatalog.Instance.Create<PackDatEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x20);
        entry.Flags  = file.View.ReadUInt32 (index_offset+0x24);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x28);
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+0x2c);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x30;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pentry = entry as PackDatEntry;
    if (null == pentry || entry.Size < 4
        || !(0 != (pentry.Flags & 0x10000) || entry.Name.HasExtension (".s")))
        return arc.File.CreateStream (entry.Offset, entry.Size);

    var input = arc.File.View.ReadBytes (entry.Offset, pentry.Size);
    if (0 != (pentry.Flags & 0x10000))
    {
        unsafe
        {
            fixed (byte* buf_raw = input)
            {
                uint* encoded = (uint*)buf_raw;
                uint key = pentry.Size >> 2;
                key ^= key << (((int)key & 7) + 8);
                for (uint i = entry.Size / 4; i != 0; --i )
                {
                    *encoded ^= key;
                    int cl = (int)(*encoded++ % 24);
                    key = Binary.RotL (key, cl);
                }
            }
        }
    }
    if (entry.Name.HasExtension (".s"))
    {
        for (int i = 0; i < input.Length; ++i)
            input[i] ^= 0xFF;
    }
    return new BinMemoryStream (input, entry.Name);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ArcPACKDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
