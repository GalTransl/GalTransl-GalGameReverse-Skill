# ComicPlayer / ArcCP3：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CP3/CM` / `GameRes.Formats.ComicPlayer.Cp3Opener` | `cp3`, `exe` | `434d3350` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Cp3Opener.TryOpen` | `if (0x5A4D == file.View.ReadUInt16 (0))` |
| `Cp3Opener.TryOpen` | `var magic = file.View.ReadString (base_offset, 8);` |
| `Cp3Opener.TryOpen` | `ushort tag = file.View.ReadUInt16 (offset);` |
| `Cp3Opener.TryOpen` | `uint name_length = file.View.ReadByte (offset);` |
| `Cp3Opener.TryOpen` | `var name = file.View.ReadString (offset + 1, name_length);` |
| `Cp3Opener.TryOpen` | `uint flags = Binary.BigEndian (file.View.ReadUInt32 (offset - 8));` |
| `Cp3Opener.TryOpen` | `entry.Size = Binary.BigEndian (file.View.ReadUInt32 (offset));` |
| `Cp3Opener.OpenEntry` | `var key = arc.File.View.ReadBytes (0x118, 0x100);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ComicPlayer.Cp3Opener

继承/接口：`ArchiveFormat`。

#### Cp3Opener

```csharp
public Cp3Opener () {
    Signatures = new[] { 0x50334D43u, 0u };
    Extensions = new[] { "cp3", "exe" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint base_offset = 0;
    if (0x5A4D == file.View.ReadUInt16 (0))
    {
        var exe = new ExeFile (file);
        base_offset = (uint)exe.Overlay.Offset + 0x100;
    }
    var magic = file.View.ReadString (base_offset, 8);
    if (magic != "CM3PKG")
        return null;

    long offset = base_offset + 0x218;
    var dir = new List<Entry> ();
    while (offset < file.MaxOffset)
    {
        ushort tag = file.View.ReadUInt16 (offset);
        if (tag == 0x5045)
            break;
        else if (tag != 0x494C)
            return null;
        offset += 6;
        uint name_length = file.View.ReadByte (offset);
        var name = file.View.ReadString (offset + 1, name_length);
        if (string.IsNullOrEmpty (name))
            return null;
        var entry = Create<CpEntry> (name);
        offset += name_length + 9;
        uint flags = Binary.BigEndian (file.View.ReadUInt32 (offset - 8));
        entry.IsPacked = (flags & 0x80000000) != 0;
        entry.IsEncrypted = (flags & 0x80000) != 0;
        entry.Offset = offset + 12;
        entry.Size = Binary.BigEndian (file.View.ReadUInt32 (offset));
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".cf3"))
            entry.Type = "script";
        dir.Add (entry);
        offset = entry.Offset + entry.Size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var cent = entry as CpEntry;
    Stream input = arc.File.CreateStream (cent.Offset, cent.Size);
    if (cent.IsEncrypted)
    {
        var key = arc.File.View.ReadBytes (0x118, 0x100);
        input = new ByteStringEncryptedStream (input, key);
    }
    if (cent.IsPacked)
        input = new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/ComicPlayer/ArcCPF.cs](ArcCPF.md)：本页引用的随包算法资料。
- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ComicPlayer/ArcCP3.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
