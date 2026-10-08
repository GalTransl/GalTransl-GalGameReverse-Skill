# ComicPlayer / ArcCPF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `CPF` / `GameRes.Formats.ComicPlayer.CpfOpener` | `cpf`, `ci`, `cml`, `exe` | `49434d39`, `434d494e`, `434d334c` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CpfOpener.TryOpen` | `if (0x5A4D == file.View.ReadUInt16 (0))` |
| `CpfOpener.TryOpen` | `var magic = file.View.ReadString (base_offset, 8);` |
| `CpfOpener.TryOpen` | `int count = file.View.ReadInt32 (base_offset + 0x108);` |
| `CpfOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x100);` |
| `CpfOpener.TryOpen` | `uint flags = file.View.ReadUInt32 (index_offset);` |
| `CpfOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset + 8) + data_offset;` |
| `CpfOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset + 12);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ComicPlayer.CpEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public bool IsEncrypted ;
```

### GameRes.Formats.ComicPlayer.CpfOpener

继承/接口：`ArchiveFormat`。

#### CpfOpener

```csharp
public CpfOpener () {
    Signatures = new[] { 0x394D4349u, 0x4E494D43u, 0x4C334D43u, 0u };
    Extensions = new[] { "cpf", "ci", "cml", "exe" };
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
    var valid_magics = new List<string> { "ICM95", "CMINST", "CM3PKG", "CM3LIB" };
    var magic = file.View.ReadString (base_offset, 8);
    if (!valid_magics.Contains (magic))
        return null;

    int count = file.View.ReadInt32 (base_offset + 0x108);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = base_offset + 0x10C;
    uint data_offset = index_offset + (uint)count * 0x110;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; i++)
    {
        var name = file.View.ReadString (index_offset, 0x100);
        if (string.IsNullOrEmpty (name))
            return null;
        var entry = Create<CpEntry> (name);
        index_offset += 0x100;
        uint flags = file.View.ReadUInt32 (index_offset);
        entry.IsPacked = (flags & 0x80000000) != 0;
        entry.Offset = file.View.ReadUInt32 (index_offset + 8) + data_offset;
        entry.Size = file.View.ReadUInt32 (index_offset + 12);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasAnyOfExtensions (".csf", ".cf3"))
            entry.Type = "script";
        dir.Add (entry);
        index_offset += 0x10;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var cent = entry as CpEntry;
    var input = arc.File.CreateStream (cent.Offset, cent.Size);
    if (cent.IsPacked)
        return new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ComicPlayer/ArcCPF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
