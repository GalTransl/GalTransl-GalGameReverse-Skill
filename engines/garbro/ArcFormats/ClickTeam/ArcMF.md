# ClickTeam / ArcMF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MFS` / `GameRes.Formats.ClickTeam.MfOpener` | `` | `77777777` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MfOpener.TryOpen` | `if (0x5A4D == file.View.ReadUInt16 (0))` |
| `MfOpener.TryOpen` | `int count = file.View.ReadInt32 (base_offset + 0x1C);` |
| `MfOpener.TryOpen` | `int name_length = file.View.ReadUInt16 (index_pos) * 2;` |
| `MfOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_pos + 4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.ClickTeam.MfOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] s_mfs_header = {
    (byte)'w', (byte)'w', (byte)'w', (byte)'w', 0x49, 0x87, 0x47, 0x12,
}
```

#### MfOpener

```csharp
public MfOpener () {
    Signatures = new uint[] { 0x77777777, 0 };
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long base_offset = 0;
    if (0x5A4D == file.View.ReadUInt16 (0))
    {
        var exe = new ExeFile (file);
        base_offset = exe.Overlay.Offset;
    }
    if (base_offset + 0x20 > file.MaxOffset || !file.View.BytesEqual (base_offset, s_mfs_header))
        return null;

    int count = file.View.ReadInt32 (base_offset + 0x1C);
    if (!IsSaneCount (count))
        return null;

    long index_pos = base_offset + 0x20;
    var dir = new List<Entry> (count);
    var name_buffer = new byte[520];
    for (int i = 0; i < count; ++i)
    {
        int name_length = file.View.ReadUInt16 (index_pos) * 2;
        if (name_length > name_buffer.Length)
            return null;
        file.View.Read (index_pos + 2, name_buffer, 0, (uint)name_length);
        var name = Encoding.Unicode.GetString (name_buffer, 0, name_length);
        index_pos += 2 + name_length;
        var entry = Create<PackedEntry> (name);
        entry.IsPacked = name != "mmfs2.dll";
        entry.Size = file.View.ReadUInt32 (index_pos + 4);
        entry.Offset = index_pos + 8;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_pos = entry.Offset + entry.Size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = (PackedEntry)entry;
    Stream input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (pent.IsPacked)
        input = new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/ClickTeam/ArcMF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
