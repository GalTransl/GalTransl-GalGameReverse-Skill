# Aims / ArcPACK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PACK/AIMS` / `GameRes.Formats.Aims.PackOpener` | `p`, `mus`, `pac` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PackOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PackOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x40);` |
| `PackOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x48);` |
| `PackOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x4C);` |
| `PackOpener.OpenEntry` | `if (null == arc \|\| !arc.File.View.AsciiEqual (entry.Offset, "LZSS"))` |
| `PackOpener.OpenEntry` | `uint unpacked_size = arc.File.View.ReadUInt32 (entry.Offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Aims.LunaArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### LunaArchive

```csharp
public LunaArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Aims.PackOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] DefaultKey = {
    0x7D, 0x73, 0xF6, 0xE4, 0xF5, 0x81, 0x5F, 0x7C, 0x78, 0x30, 0xC2, 0x36, 0xEA, 0x3E, 0x8A, 0x76,
    0xF7, 0xE0, 0x48, 0xB5, 0x85, 0xD7, 0x77, 0x49, 0x4C, 0x3D, 0xF5, 0x0C, 0xBB, 0xFB, 0x2E, 0x44,
    0xFE, 0x25, 0xB7, 0xEB, 0xC7, 0xD9, 0x33, 0xAB, 0xA8, 0x2C, 0x64, 0xE8, 0xF0, 0xBD, 0xEB, 0x8D,
    0x9D, 0x1D, 0xA2, 0xFC, 0x59, 0x09, 0xAA, 0xA4,
}
```

#### PackOpener

```csharp
public PackOpener () {
    Extensions = new string[] { "p", "mus", "pac" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 8;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x40);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x48);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x4C);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x50;
    }
    return new LunaArchive (file, this, dir, DefaultKey);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var larc = arc as LunaArchive;
    if (null == arc || !arc.File.View.AsciiEqual (entry.Offset, "LZSS"))
        return base.OpenEntry (arc, entry);

    uint unpacked_size = arc.File.View.ReadUInt32 (entry.Offset+4);
    Stream input = arc.File.CreateStream (entry.Offset+8, entry.Size-8);
    if (larc.Key != null)
    {
        var bf = new Blowfish (larc.Key);
        input = new InputCryptoStream (input, bf.CreateDecryptor());
        return new LimitStream (input, unpacked_size);
    }
    else
    {
        var lz = new LzssStream (input);
        lz.Config.FrameInitPos = 0xFF0;
        return lz;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Blowfish.cs](../Blowfish.md)：本页引用的随包算法资料。
- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Aims/ArcPACK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
