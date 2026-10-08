# Moonhir / ArcFPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FPK/MOONHIR` / `GameRes.Formats.MoonhirGames.FpkOpener` | `fpk` | `46504b00` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `FpkOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "0100"))` |
| `FpkOpener.TryOpen` | `int count = file.View.ReadInt32 (0xC);` |
| `FpkOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `FpkOpener.TryOpen` | `var name = file.View.ReadString (index_offset+12, 12);` |
| `FpkOpener.TryOpen` | `entry.IsEncrypted = 0 != file.View.ReadUInt32 (index_offset);` |
| `FpkOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4);` |
| `FpkOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+8);` |
| `FpkOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `FpkOpener.OpenEntry` | `int length = LittleEndian.ToInt32 (data, data.Length-8);` |
| `FpkOpener.OpenEntry` | `if (!Binary.AsciiEqual (header, "FBX\x01"))` |
| `FpkOpener.OpenEntry` | `int packed_size = LittleEndian.ToInt32 (header, 8);` |
| `FpkOpener.OpenEntry` | `int unpacked_size = LittleEndian.ToInt32 (header, 0xC);` |
| `FpkOpener.FindKey` | `uint t1 = file.View.ReadUInt32 (offset+4);` |
| `FpkOpener.FindKey` | `uint t0 = file.View.ReadUInt32 (offset);` |
| `FpkOpener.UnpackFbx` | `ctl = input.ReadByte();` |
| `FpkOpener.UnpackFbx` | `output[dst++] = (byte)input.ReadByte();` |
| `FpkOpener.UnpackFbx` | `count = input.ReadByte();` |
| `FpkOpener.UnpackFbx` | `offset  = input.ReadByte() << 8;` |
| `FpkOpener.UnpackFbx` | `offset \|= input.ReadByte();` |
| `FpkOpener.UnpackFbx` | `int exctl = input.ReadByte();` |
| `FpkOpener.UnpackFbx` | `count = count << 8 \| input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.MoonhirGames.FpkEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public bool IsEncrypted ;
```

### GameRes.Formats.MoonhirGames.FpkArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly uint Key ;
```

#### FpkArchive

```csharp
public FpkArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, uint key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.MoonhirGames.FpkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public static uint[] KnownKeys = { 0 }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "0100"))
        return null;
    int count = file.View.ReadInt32 (0xC);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (8);

    var arc_name = Path.GetFileName (file.Name);
    var fbx_type = arc_name.StartsWith ("scr", StringComparison.OrdinalIgnoreCase) ? "" : "image";
    var dir = new List<Entry> (count);
    bool has_encrypted = false;
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset+12, 12);
        var entry = Create<FpkEntry> (name);
        entry.IsEncrypted = 0 != file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset+4);
        entry.Size   = file.View.ReadUInt32 (index_offset+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".fbx"))
            entry.Type = fbx_type;
        has_encrypted = has_encrypted || entry.IsEncrypted;
        dir.Add (entry);
        index_offset += 0x18;
    }
    if (!has_encrypted)
        return new ArcFile (file, this, dir);
    var enc_entry = dir.Cast<FpkEntry>().FirstOrDefault (e => e.IsEncrypted && e.Size > 8);
    if (null == enc_entry)
        return new ArcFile (file, this, dir);
    var key = FindKey (file, enc_entry);
    if (null == key)
    {
        Trace.WriteLine (string.Format ("{0}: unknown encryption key", file.Name), "[FPK]");
        return new ArcFile (file, this, dir);
    }
    return new FpkArchive (file, this, dir, key.Value);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var farc = arc as FpkArchive;
    var fent = entry as FpkEntry;
    Stream input;
    byte[] header;
    if (null == farc || null == fent || !fent.IsEncrypted)
    {
        if (fent != null && fent.IsEncrypted)
            throw new UnknownEncryptionScheme();
        input = arc.File.CreateStream (entry.Offset, entry.Size);
        header = new byte[0x10];
        input.Read (header, 0, 0x10);
        input.Position = 0;
    }
    else
    {
        var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
        Decrypt (data, 0, data.Length, farc.Key);
        int length = LittleEndian.ToInt32 (data, data.Length-8);
        input = new BinMemoryStream (data, 0, length, entry.Name);
        header = data;
    }
    if (!Binary.AsciiEqual (header, "FBX\x01"))
        return input;
    using (input)
    {
        int packed_size = LittleEndian.ToInt32 (header, 8);
        int unpacked_size = LittleEndian.ToInt32 (header, 0xC);
        input.Position = header[7];
        var unpacked = UnpackFbx (input, packed_size, unpacked_size);
        return new BinMemoryStream (unpacked, entry.Name);
    }
}
```

#### FindKey

```csharp
uint? FindKey (ArcView file, Entry entry) {
    if (entry.Size < 8)
        return null;
    var offset = entry.Offset + entry.Size - 8;
    uint t1 = file.View.ReadUInt32 (offset+4);
    uint t0 = file.View.ReadUInt32 (offset);

    foreach (uint key in KnownKeys)
    {
        uint k1 = key + entry.Size - 4;
        uint k2 = ((key - ((t1 - k1) ^ key)) >> 7) ^ ((k1 + key) << 7);
        uint test_length = ((((t0 - (k1 - 3)) ^ k2) + 3) & ~3u) + 8;
        if (entry.Size == test_length)
            return key;
    }
    return null;
}
```

#### Decrypt

```csharp
unsafe void Decrypt (byte[] data, int index, int length, uint key) {
    if (length < 8)
        return;
    fixed (byte* data8 = &data[index])
    {
        uint* data32 = (uint*)data8;
        uint* dptr = data32 + length / 4 - 1;
        uint k1 = key + (uint)length - 4;
        uint k2 = key;
        while (dptr >= data32)
        {
            *dptr = (*dptr - k1) ^ k2;
            k2 = ((k2 - *dptr) >> 7) ^ ((k1 + k2) << 7);
            k1 -= 3;
            --dptr;
        }
    }
}
```

#### UnpackFbx

```csharp
byte[] UnpackFbx (Stream input, int packed_size, int unpacked_size) {
    var output = new byte[unpacked_size];
    int dst = 0;
    int ctl = 1;
    while (dst < output.Length)
    {
        if (1 == ctl)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            ctl |= 0x100;
        }
        int count, offset;
        switch (ctl & 3)
        {
        case 0:
            output[dst++] = (byte)input.ReadByte();
            break;
        case 1:
            count = input.ReadByte();
            if (-1 == count)
                return output;
            count = Math.Min (count + 2, output.Length - dst);
            input.Read (output, dst, count);
            dst += count;
            break;
        case 2:
            offset  = input.ReadByte() << 8;
            offset |= input.ReadByte();
            if (-1 == offset)
                return output;
            count = Math.Min ((offset & 0x1F) + 4, output.Length - dst);
            offset >>= 5;
            Binary.CopyOverlapped (output, dst - offset - 1, dst, count);
            dst += count;
            break;
        case 3:
            int exctl = input.ReadByte();
            if (-1 == exctl)
                return output;
            count = exctl & 0x3F;
            switch (exctl >> 6)
            {
            case 0:
                count = count << 8 | input.ReadByte();
                if (-1 == count)
                    return output;
                count = Math.Min (count + 0x102, output.Length - dst);
                input.Read (output, dst, count);
                dst += count;
                break;
            case 1:
                offset  = input.ReadByte() << 8;
                offset |= input.ReadByte();
                count = count << 5 | offset & 0x1F;
                count = Math.Min (count + 0x24, output.Length - dst);
                offset >>= 5;
                Binary.CopyOverlapped (output, dst - offset - 1, dst, count);
                dst += count;
                break;
            case 3:
                input.Seek (count, SeekOrigin.Current);
                ctl = 1 << 2;
                break;
            default:
                break;
            }
            break;
        }
        ctl >>= 2;
    }
    return output;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Moonhir/ArcFPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
