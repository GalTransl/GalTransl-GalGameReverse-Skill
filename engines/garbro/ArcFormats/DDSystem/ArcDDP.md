# DDSystem / ArcDDP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DDP2` / `GameRes.Formats.DDSystem.Ddp2Opener` | `dat` | `44445032` | `False` |
| `DDP3` / `GameRes.Formats.DDSystem.Ddp3Opener` | `dat` | `44445033` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Ddp2Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Ddp2Opener.TryOpen` | `Offset      = file.View.ReadUInt32 (index_offset),` |
| `Ddp2Opener.TryOpen` | `UnpackedSize = file.View.ReadUInt32 (index_offset+4),` |
| `Ddp2Opener.TryOpen` | `Size        = file.View.ReadUInt32 (index_offset+8),` |
| `Ddp2Opener.DetectFileTypes` | `signature = LittleEndian.ToUInt32 (signature_buffer, 0);` |
| `Ddp2Opener.DetectFileTypes` | `signature = file.View.ReadUInt32 (entry.Offset);` |
| `Ddp2Opener.OpenEntry` | `if (data.Length > 16 && Binary.AsciiEqual (data, 0, "DDSxHXB"))` |
| `Ddp3Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Ddp3Opener.TryOpen` | `int entry_size = file.View.ReadByte (index_offset);` |
| `Ddp3Opener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset+1),` |
| `Ddp3Opener.TryOpen` | `UnpackedSize = file.View.ReadUInt32 (index_offset+5),` |
| `Ddp3Opener.TryOpen` | `Size = file.View.ReadUInt32 (index_offset+9),` |
| `Ddp3Opener.TryOpen` | `Name = file.View.ReadString (index_offset+17, (uint)entry_size-17),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DDSystem.Ddp2Opener

继承/接口：`ArchiveFormat`。

#### Ddp2Opener

```csharp
public Ddp2Opener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    uint index_offset = 0x20;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new PackedEntry {
            Offset      = file.View.ReadUInt32 (index_offset),
            UnpackedSize = file.View.ReadUInt32 (index_offset+4),
            Size        = file.View.ReadUInt32 (index_offset+8),
            Name        = string.Format ("{0}#{1:D5}", base_name, i),
        };
        entry.IsPacked = entry.Size != 0;
        if (!entry.IsPacked)
            entry.Size = entry.UnpackedSize;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 0x10;
        dir.Add (entry);
    }
    DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

#### DetectFileTypes

```csharp
internal static void DetectFileTypes (ArcView file, List<Entry> dir) {
    byte[] signature_buffer = new byte[4];
    foreach (PackedEntry entry in dir)
    {
        uint signature;
        if (entry.IsPacked)
        {
            using (var input = file.CreateStream (entry.Offset, Math.Min (entry.Size, 0x20u)))
            using (var reader = new ShsCompression (input))
            {
                reader.Unpack (signature_buffer);
                signature = LittleEndian.ToUInt32 (signature_buffer, 0);
            }
        }
        else
        {
            signature = file.View.ReadUInt32 (entry.Offset);
        }
        if (0x78534444 == signature)
        {
            entry.Type = "script";
            entry.Name = Path.ChangeExtension (entry.Name, "hxb");
        }
        else if (0 != signature)
        {
            IResource res;
            if (0x020000 == signature || 0x0A0000 == signature)
                res = ImageFormat.Tga;
            else
                res = AutoEntry.DetectFileType (signature);
            if (res != null)
                entry.ChangeType (res);
        }
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return input;
    var data = new byte[pent.UnpackedSize];
    using (var reader = new ShsCompression (input))
    {
        reader.Unpack (data);
        if (data.Length > 16 && Binary.AsciiEqual (data, 0, "DDSxHXB"))
            DecryptHxb (data);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### DecryptHxb

```csharp
internal void DecryptHxb (byte[] data) {
    int length = data[8] << 16 | data[9] << 8 | data[10];
    if (length != data.Length)
        return;
    int key = (((length << 5) ^ 0xA5) * (length + 0x6F349)) ^ 0x34A9B129;
    var key_bits = new byte[4];
    LittleEndian.Pack (key, key_bits, 0);
    for (int i = 0x10; i < data.Length; ++i)
    {
        data[i] ^= key_bits[i & 3];
    }
}
```

### GameRes.Formats.DDSystem.Ddp3Opener

继承/接口：`Ddp2Opener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    var index = Him5Opener.ReadIndex (file, 0x20, count);
    var dir = new List<Entry>();
    foreach (var section in index)
    {
        int index_offset = section.Item1;
        for (int section_size = section.Item2; section_size > 0; )
        {
            int entry_size = file.View.ReadByte (index_offset);
            if (entry_size < 17)
                break;
            var entry = new PackedEntry {
                Offset = file.View.ReadUInt32 (index_offset+1),
                UnpackedSize = file.View.ReadUInt32 (index_offset+5),
                Size = file.View.ReadUInt32 (index_offset+9),
                Name = file.View.ReadString (index_offset+17, (uint)entry_size-17),
            };
            entry.IsPacked = entry.Size != 0;
            if (!entry.IsPacked)
                entry.Size = entry.UnpackedSize;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            index_offset += entry_size;
            section_size -= entry_size;
            dir.Add (entry);
        }
    }
    DetectFileTypes (file, dir);
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/SHSystem/ArcHXP.cs](../SHSystem/ArcHXP.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/DDSystem/ArcDDP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
