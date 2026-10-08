# KiriKiri / ArcXPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `XPK` / `GameRes.Formats.KiriKiri.XpkOpener` | `xpk` | `58504b31` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `XpkOpener.TryOpen` | `if (0x5A4D == file.View.ReadUInt16 (0))` |
| `XpkOpener.TryOpen` | `index.ReadInt16();` |
| `XpkOpener.TryOpen` | `var name = index.ReadCString();` |
| `XpkOpener.ReadUInt` | `if (input.ReadByte() != 4)` |
| `XpkOpener.ReadUInt` | `return Binary.BigEndian (input.ReadUInt32());` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KiriKiri.XpkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] SignatureBytes = Encoding.ASCII.GetBytes ("XPK1\x1A") ;
```

#### XpkOpener

```csharp
public XpkOpener () {
    Signatures = new uint[] { 0x314B5058, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long base_offset = 0;
    if (0x5A4D == file.View.ReadUInt16 (0))
        base_offset = Xp3Opener.SkipExeHeader (file, SignatureBytes);
    if (!file.View.BytesEqual (base_offset, SignatureBytes))
        return null;
    using (var index = file.CreateStream())
    {
        index.Position = base_offset+10;
        int count = (int)ReadUInt (index);
        if (!IsSaneCount (count))
            return null;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            long offset = ReadUInt (index) + base_offset;
            uint size = ReadUInt (index);
            uint unpacked_size = ReadUInt (index);
            index.ReadInt16();
            var name = index.ReadCString();
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset = offset;
            entry.Size   = size;
            entry.UnpackedSize = unpacked_size;
            if (!entry.CheckPlacement (file.MaxOffset) && !(offset == file.MaxOffset && size == 0))
                return null;
            dir.Add (entry);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### ReadUInt

```csharp
internal static uint ReadUInt (IBinaryStream input) {
    if (input.ReadByte() != 4)
        throw new InvalidFormatException();
    return Binary.BigEndian (input.ReadUInt32());
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    PackedEntry packed_entry = entry as PackedEntry;
    if (null == packed_entry || packed_entry.Size == packed_entry.UnpackedSize)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    return new ZLibStream (arc.File.CreateStream (entry.Offset, entry.Size), CompressionMode.Decompress);
}
```

## 配套算法与外部条件

- [ArcFormats/KiriKiri/ArcXP3.cs](ArcXP3.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/KiriKiri/ArcXPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
