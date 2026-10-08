# DenSDK / ArcDAF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAF1` / `GameRes.Formats.DenSdk.Daf1Opener` | `dat` | `44414631` | `False` |
| `DAF2` / `GameRes.Formats.DenSdk.Daf2Opener` | `dat` | `44414632` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Daf1Opener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (4);` |
| `Daf1Opener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `Daf1Opener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (0x10);` |
| `Daf1Opener.TryOpen` | `uint entry_size = file.View.ReadUInt32 (index_offset);` |
| `Daf1Opener.TryOpen` | `var name = file.View.ReadString (index_offset+0x18, entry_size-0x18);` |
| `Daf1Opener.TryOpen` | `entry.Offset        = file.View.ReadUInt32(index_offset+4);` |
| `Daf1Opener.TryOpen` | `entry.Size          = file.View.ReadUInt32(index_offset+8);` |
| `Daf1Opener.TryOpen` | `entry.UnpackedSize  = file.View.ReadUInt32 (index_offset+0xC);` |
| `Daf1Opener.TryOpen` | `entry.IsPacked      = file.View.ReadInt32(index_offset+0x14) != 0;` |
| `Daf2Opener.TryOpen` | `uint key = (uint)(file.View.ReadByte (0x20) << 24` |
| `Daf2Opener.TryOpen` | `\| file.View.ReadByte (0x25) << 16` |
| `Daf2Opener.TryOpen` | `\| file.View.ReadByte (0x2A) << 8` |
| `Daf2Opener.TryOpen` | `\| file.View.ReadByte (0x2F));` |
| `Daf2Opener.TryOpen` | `int count = file.View.ReadInt32 (8) ^ (int)key;` |
| `Daf2Opener.TryOpen` | `uint packed_size = file.View.ReadUInt32 (0x10) ^ key;` |
| `Daf2Opener.TryOpen` | `uint unpacked_size = file.View.ReadUInt32 (0x14) ^ key;` |
| `Daf2Opener.TryOpen` | `uint base_offset = file.View.ReadUInt32 (0x1C) ^ key;` |
| `Daf2Opener.TryOpen` | `bool is_packed = file.View.ReadInt32 (0x18) == 1;` |
| `Daf2Opener.TryOpen` | `int entry_size = LittleEndian.ToInt32 (index, index_offset) ^ (int)key;` |
| `Daf2Opener.TryOpen` | `entry.Offset        = base_offset + (LittleEndian.ToUInt32 (index, index_offset+4) ^ key);` |
| `Daf2Opener.TryOpen` | `entry.Size          = LittleEndian.ToUInt32 (index, index_offset+8) ^ key;` |
| `Daf2Opener.TryOpen` | `entry.UnpackedSize  = LittleEndian.ToUInt32 (index, index_offset+0xC) ^ key;` |
| `Daf2Opener.TryOpen` | `entry.IsPacked      = LittleEndian.ToInt32 (index, index_offset+0x30) != 0;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DenSdk.Daf1Opener

继承/接口：`ArchiveFormat`。

#### Daf1Opener

```csharp
public Daf1Opener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint index_offset = file.View.ReadUInt32 (4);
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count) || index_offset >= file.MaxOffset)
        return null;
    uint data_offset = file.View.ReadUInt32 (0x10);
    if (data_offset <= index_offset || data_offset > file.MaxOffset)
        return null;
    file.View.Reserve (index_offset, data_offset-index_offset);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint entry_size = file.View.ReadUInt32 (index_offset);
        if (entry_size <= 0x18)
            return null;
        var name = file.View.ReadString (index_offset+0x18, entry_size-0x18);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset        = file.View.ReadUInt32(index_offset+4);
        entry.Size          = file.View.ReadUInt32(index_offset+8);
        entry.UnpackedSize  = file.View.ReadUInt32 (index_offset+0xC);
        entry.IsPacked      = file.View.ReadInt32(index_offset+0x14) != 0;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

### GameRes.Formats.DenSdk.Daf2Opener

继承/接口：`Daf1Opener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint key = (uint)(file.View.ReadByte (0x20) << 24
                    | file.View.ReadByte (0x25) << 16
                    | file.View.ReadByte (0x2A) << 8
                    | file.View.ReadByte (0x2F));
    int count = file.View.ReadInt32 (8) ^ (int)key;
    if (!IsSaneCount (count))
        return null;
    uint packed_size = file.View.ReadUInt32 (0x10) ^ key;
    uint unpacked_size = file.View.ReadUInt32 (0x14) ^ key;
    uint base_offset = file.View.ReadUInt32 (0x1C) ^ key;
    byte[] index = new byte[unpacked_size];
    bool is_packed = file.View.ReadInt32 (0x18) == 1;
    if (is_packed)
    {
        using (var input = file.CreateStream (0x30, packed_size))
        using (var zindex = new ZLibStream (input, CompressionMode.Decompress))
            zindex.Read (index, 0, index.Length);
        base_offset = 0x30 + packed_size;
    }
    else
    {
        file.View.Read (0x30, index, 0, unpacked_size);
    }
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int entry_size = LittleEndian.ToInt32 (index, index_offset) ^ (int)key;
        if (entry_size < 0x30 || entry_size > index.Length-index_offset)
            return null;
        var name = Binary.GetCString (index, index_offset+0x34, entry_size-0x34);
        var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
        entry.Offset        = base_offset + (LittleEndian.ToUInt32 (index, index_offset+4) ^ key);
        entry.Size          = LittleEndian.ToUInt32 (index, index_offset+8) ^ key;
        entry.UnpackedSize  = LittleEndian.ToUInt32 (index, index_offset+0xC) ^ key;
        entry.IsPacked      = LittleEndian.ToInt32 (index, index_offset+0x30) != 0;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/DenSDK/ArcDAF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
