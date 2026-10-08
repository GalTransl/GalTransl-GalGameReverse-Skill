# Witch / ArcPCD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCD/IMAGE` / `GameRes.Formats.Witch.ImageDataOpener` | `pcd` | `494d4147` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ImageDataOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "IMAGEDATE "))` |
| `ImageDataOpener.TryOpen` | `int count = file.View.ReadInt32 (0xA);` |
| `ImageDataOpener.TryOpen` | `int left    = file.View.ReadInt32 (index_offset+8);` |
| `ImageDataOpener.TryOpen` | `int top     = file.View.ReadInt32 (index_offset+0xC);` |
| `ImageDataOpener.TryOpen` | `int right   = file.View.ReadInt32 (index_offset+0x10);` |
| `ImageDataOpener.TryOpen` | `int bottom  = file.View.ReadInt32 (index_offset+0x14);` |
| `ImageDataOpener.TryOpen` | `int name_length = file.View.ReadInt32 (index_offset);` |
| `ImageDataOpener.TryOpen` | `name_length = file.View.ReadInt32 (index_offset);` |
| `ImageDataOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset),` |
| `ImageDataOpener.OpenEntry` | `uint format_id = arc.File.View.ReadUInt32 (entry.Offset);` |
| `ImageDataOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Witch.PcdEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public ImageMetaData    Info ;
```

### GameRes.Formats.Witch.ImageDataOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "IMAGEDATE "))
        return null;
    int count = file.View.ReadInt32 (0xA);
    if (!IsSaneCount (count))
        return null;
    long index_offset = 0xE;
    var dir = new List<Entry> (count);
    var name_buffer = new byte[0x100];
    for (int i = 0; i < count; ++i)
    {
        int left    = file.View.ReadInt32 (index_offset+8);
        int top     = file.View.ReadInt32 (index_offset+0xC);
        int right   = file.View.ReadInt32 (index_offset+0x10);
        int bottom  = file.View.ReadInt32 (index_offset+0x14);
        index_offset += 0x18;
        int name_length = file.View.ReadInt32 (index_offset);
        if (name_length <= 0)
            return null;
        if (name_length > name_buffer.Length)
            name_buffer = new byte[name_length];
        file.View.Read (index_offset+4, name_buffer, 0, (uint)name_length);
        DecryptName (name_buffer, 0, name_length);
        var name = Binary.GetCString (name_buffer, 0, name_length);
        index_offset += 4 + name_length;

        name_length = file.View.ReadInt32 (index_offset);
        if (name_length > name_buffer.Length)
            name_buffer = new byte[name_length];
        file.View.Read (index_offset+4, name_buffer, 0, (uint)name_length);
        DecryptName (name_buffer, 0, name_length);
        var frame_name = Binary.GetCString (name_buffer, 0, name_length);
        if (frame_name != "NO NAME")
        {
            frame_name = frame_name.Replace ('/', '／');
            name = Path.Combine (name, frame_name);
        }
        index_offset += 4 + name_length;

        var entry = new PcdEntry {
            Name = name,
            Type = "image",
            Offset = file.View.ReadUInt32 (index_offset),
        };
        if (entry.Offset > file.MaxOffset)
            return null;
        entry.Info = new ImageMetaData {
            Width  = (uint)(right - left),
            Height = (uint)(bottom - top),
            OffsetX = left,
            OffsetY = top,
            BPP = 32,
        };
        dir.Add (entry);
        index_offset += 4;
    }
    SetAdjacentEntriesSize (dir, file.MaxOffset);
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    uint format_id = arc.File.View.ReadUInt32 (entry.Offset);
    switch (format_id)
    {
    case 0:
        return arc.File.CreateStream (entry.Offset+0x20, entry.Size-0x20);
    case 1:
    case 2:
        break;
    default:
        return arc.File.CreateStream (entry.Offset, entry.Size);
    }
    var pent = (PcdEntry)entry;
    if (!pent.IsPacked)
    {
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);
    }
    var input = arc.File.CreateStream (entry.Offset+0x20, entry.Size-0x20);
    if (1 == format_id)
        return new ZLibStream (input, CompressionMode.Decompress);
    else
        return new BZip2InputStream (input);
}
```

#### DecryptName

```csharp
internal static void DecryptName (byte[] buffer, int pos, int length) {
    for (int i = 0; i < length; ++i)
        buffer[pos+i] ^= 0xFF;
}
```

#### SetAdjacentEntriesSize

```csharp
internal static void SetAdjacentEntriesSize (List<Entry> dir, long max_offset) {
    int count = dir.Count;
    for (int i = 1; i < count; ++i)
        dir[i-1].Size = (uint)(dir[i].Offset - dir[i-1].Offset);
    dir[count-1].Size = (uint)(max_offset - dir[count-1].Offset);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Witch/ArcPCD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
