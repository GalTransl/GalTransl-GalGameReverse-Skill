# EmonEngine / ArcEME：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `EME` / `GameRes.Formats.EmonEngine.EmeOpener` | `eme`, `rre` | `52524544` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `EmeOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "ATA "))` |
| `EmeOpener.TryOpen` | `int count = file.View.ReadInt32 (file.MaxOffset-4);` |
| `EmeOpener.TryOpen` | `var key = file.View.ReadBytes (index_offset - 40, 40);` |
| `EmeOpener.TryOpen` | `var index = file.View.ReadBytes (index_offset, index_size);` |
| `EmeOpener.TryOpen` | `entry.LzssFrameSize = LittleEndian.ToUInt16 (index, current_offset+0x40);` |
| `EmeOpener.TryOpen` | `entry.LzssInitPos   = LittleEndian.ToUInt16 (index, current_offset+0x42);` |
| `EmeOpener.TryOpen` | `entry.SubType       = LittleEndian.ToInt32  (index, current_offset+0x48);` |
| `EmeOpener.TryOpen` | `entry.Size          = LittleEndian.ToUInt32 (index, current_offset+0x4C);` |
| `EmeOpener.TryOpen` | `entry.UnpackedSize  = LittleEndian.ToUInt32 (index, current_offset+0x50);` |
| `EmeOpener.TryOpen` | `entry.Offset        = LittleEndian.ToUInt32 (index, current_offset+0x54);` |
| `EmeOpener.OpenScript` | `var header = arc.File.View.ReadBytes (entry.Offset, 12);` |
| `EmeOpener.OpenScript` | `int unpacked_size = LittleEndian.ToInt32 (header, 4);` |
| `EmeOpener.OpenScript` | `uint packed_size = LittleEndian.ToUInt32 (header, 0);` |
| `EmeOpener.OpenT5` | `var header = arc.File.View.ReadBytes (entry.Offset, 4);` |
| `EmeOpener.Decrypt` | `uint key = LittleEndian.ToUInt32 (routine, key_index);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.EmonEngine.EmeOpener

继承/接口：`ArchiveFormat`。

#### EmeOpener

```csharp
public EmeOpener () {
    Extensions = new string[] { "eme", "rre" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "ATA "))
        return null;
    int count = file.View.ReadInt32 (file.MaxOffset-4);
    if (!IsSaneCount (count))
        return null;

    uint index_size = (uint)count * 0x60;
    var index_offset = file.MaxOffset - 4 - index_size;
    var key = file.View.ReadBytes (index_offset - 40, 40);
    var index = file.View.ReadBytes (index_offset, index_size);

    int current_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        Decrypt (index, current_offset, 0x60, key);
        var name = Binary.GetCString (index, current_offset, 0x40);
        var entry = FormatCatalog.Instance.Create<EmEntry> (name);
        entry.LzssFrameSize = LittleEndian.ToUInt16 (index, current_offset+0x40);
        entry.LzssInitPos   = LittleEndian.ToUInt16 (index, current_offset+0x42);
        if (entry.LzssFrameSize != 0)
            entry.LzssInitPos = (entry.LzssFrameSize - entry.LzssInitPos) % entry.LzssFrameSize;
        entry.SubType       = LittleEndian.ToInt32  (index, current_offset+0x48);
        entry.Size          = LittleEndian.ToUInt32 (index, current_offset+0x4C);
        entry.UnpackedSize  = LittleEndian.ToUInt32 (index, current_offset+0x50);
        entry.Offset        = LittleEndian.ToUInt32 (index, current_offset+0x54);
        entry.IsPacked      = entry.UnpackedSize != entry.Size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (3 == entry.SubType)
            entry.Type = "script";
        else if (4 == entry.SubType)
            entry.Type = "image";
        dir.Add (entry);
        current_offset += 0x60;
    }
    return new EmeArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var ement = entry as EmEntry;
    var emarc = arc as EmeArchive;
    if (null == ement || null == emarc)
        return base.OpenEntry (arc, entry);
    if (3 == ement.SubType)
        return OpenScript (emarc, ement);
    else if (5 == ement.SubType && entry.Size > 4)
        return OpenT5 (emarc, ement);
    else
        return base.OpenEntry (arc, entry);
}
```

#### OpenScript

```csharp
Stream OpenScript (EmeArchive arc, EmEntry entry) {
    var header = arc.File.View.ReadBytes (entry.Offset, 12);
    Decrypt (header, 0, 12, arc.Key);
    if (0 == entry.LzssFrameSize)
    {
        var input = arc.File.CreateStream (entry.Offset+12, entry.Size);
        return new PrefixStream (header, input);
    }
    int unpacked_size = LittleEndian.ToInt32 (header, 4);
    if (0 != unpacked_size && unpacked_size < entry.UnpackedSize)
    {
        uint packed_size = LittleEndian.ToUInt32 (header, 0);
        int part1_size = (int)entry.UnpackedSize - unpacked_size;
        var data = new byte[entry.UnpackedSize];
        using (var input = arc.File.CreateStream (entry.Offset+12+packed_size, entry.Size))
        using (var lzss = new LzssStream (input))
        {
            lzss.Config.FrameSize = entry.LzssFrameSize;
            lzss.Config.FrameInitPos = entry.LzssInitPos;
            lzss.Read (data, 0, part1_size);
        }
        using (var input = arc.File.CreateStream (entry.Offset+12, packed_size))
        using (var lzss = new LzssStream (input))
        {
            lzss.Config.FrameSize = entry.LzssFrameSize;
            lzss.Config.FrameInitPos = entry.LzssInitPos;
            lzss.Read (data, part1_size, unpacked_size);
        }
        return new BinMemoryStream (data, entry.Name);
    }
    else
    {
        var input = arc.File.CreateStream (entry.Offset+12, entry.Size);
        var lzss = new LzssStream (input);
        lzss.Config.FrameSize = entry.LzssFrameSize;
        lzss.Config.FrameInitPos = entry.LzssInitPos;
        return lzss;
    }
}
```

#### OpenT5

```csharp
Stream OpenT5 (EmeArchive arc, EmEntry entry) {
    var header = arc.File.View.ReadBytes (entry.Offset, 4);
    Decrypt (header, 0, 4, arc.Key);
    var input = arc.File.CreateStream (entry.Offset+4, entry.Size-4);
    return new PrefixStream (header, input);
}
```

#### Decrypt

```csharp
internal static unsafe void Decrypt (byte[] buffer, int offset, int length, byte[] routine) {
    if (null == buffer)
        throw new ArgumentNullException ("buffer", "Buffer cannot be null.");
    if (offset < 0)
        throw new ArgumentOutOfRangeException ("offset", "Buffer offset should be non-negative.");
    if (buffer.Length - offset < length)
        throw new ArgumentException ("Buffer offset and length are out of bounds.");
    fixed (byte* data8 = &buffer[offset])
    {
        uint* data32 = (uint*)data8;
        int length32 = length / 4;
        int key_index = routine.Length;
        for (int i = 7; i >= 0; --i)
        {
            key_index -= 4;
            uint key = LittleEndian.ToUInt32 (routine, key_index);
            switch (routine[i])
            {
            case 1:
                for (int j = 0; j < length32; ++j)
                    data32[j] ^= key;
                break;
            case 2:
                for (int j = 0; j < length32; ++j)
                {
                    uint v = data32[j];
                    data32[j] = v ^ key;
                    key = v;
                }
                break;
            case 4:
                for (int j = 0; j < length32; ++j)
                    data32[j] = ShiftValue (data32[j], key);
                break;
            case 8:
                InitTable (buffer, offset, length, key);
                break;
            }
        }
    }
}
```

#### ShiftValue

```csharp
static uint ShiftValue (uint val, uint key) {
    int shift = 0;
    uint result = 0;
    for (int i = 0; i < 32; ++i)
    {
        shift += (int)key;
        result |= ((val >> i) & 1) << shift;
    }
    return result;
}
```

#### InitTable

```csharp
static void InitTable (byte[] buffer, int offset, int length, uint key) {
    var table = new byte[length];
    int x = 0;
    for (int i = 0; i < length; ++i)
    {
        x += (int)key;
        while (x >= length)
            x -= length;
        table[x] = buffer[offset+i];
    }
    Buffer.BlockCopy (table, 0, buffer, offset, length);
}
```

### GameRes.Formats.EmonEngine.EmEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int LzssFrameSize ;

public int LzssInitPos ;

public int SubType ;
```

### GameRes.Formats.EmonEngine.EmeArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] Key ;
```

#### EmeArchive

```csharp
public EmeArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    Key = key;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/EmonEngine/ArcEME.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
