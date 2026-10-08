# Macromedia / ArcDXR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DXR` / `GameRes.Formats.Macromedia.DxrOpener` | `dxr`, `cxt`, `cct`, `dcr`, `dir`, `exe` | `58464952`, `52494658`, `4d5a9000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DxrOpener.TryOpen` | `if (file.View.AsciiEqual (0, "MZ"))` |
| `DxrOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (base_offset);` |
| `DxrOpener.OpenEntry` | `uint offset = Binary.BigEndian (input.ReadUInt32());` |
| `DxrOpener.OpenEntry` | `uint length = Binary.BigEndian (input.ReadUInt32());` |
| `DxrOpener.OpenEntry` | `var text = input.ReadBytes ((int)length);` |
| `DxrOpener.LookForXfir` | `if (file.View.AsciiEqual (pos, "10JP") \|\| file.View.AsciiEqual (pos, "59JP"))` |
| `DxrOpener.LookForXfir` | `pos = file.View.ReadUInt32 (pos+4);` |
| `DxrOpener.LookForXfir` | `if (pos >= file.MaxOffset \|\| !file.View.AsciiEqual (pos, "XFIR"))` |
| `DxrOpener.LookForXfir` | `if (!file.View.AsciiEqual (pos+8, "LPPA"))` |
| `DxrOpener.LookForXfir` | `if (file.View.AsciiEqual (entry.Offset-8, "XFIR")` |
| `DxrOpener.LookForXfir` | `&& !file.View.AsciiEqual (entry.Offset, "artX"))` |
| `SoundEntry.DeserializeHeader` | `Channels              = (ushort)BigEndian.ToUInt32 (header, 0x4C),` |
| `SoundEntry.DeserializeHeader` | `SamplesPerSecond      = BigEndian.ToUInt32 (header, 0x2C),` |
| `SoundEntry.DeserializeHeader` | `AverageBytesPerSecond = BigEndian.ToUInt32 (header, 0x30),` |
| `SoundEntry.DeserializeHeader` | `BlockAlign            = (ushort)BigEndian.ToUInt32 (header, 0x50),` |
| `SoundEntry.DeserializeHeader` | `BitsPerSample         = (ushort)BigEndian.ToUInt32 (header, 0x44),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Macromedia.DxrOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public const uint SignatureXFIR = 0x52494658u ;

public const uint SignatureRIFX = 0x58464952u ;

internal static readonly HashSet<string> RawChunks = new HashSet<string> {
    "RTE0", "RTE1", "FXmp", "VWFI", "VWSC", "Lscr", "STXT", "XMED", "File"
}

internal bool ConvertText = true ;

static readonly Regex ForbiddenCharsRe = new Regex (@"[:?*<>/\\]") ;

static readonly byte[] s_xfir = { (byte)'X', (byte)'F', (byte)'I', (byte)'R' }
```

#### DxrOpener

```csharp
public DxrOpener () {
    Extensions = new[] { "dxr", "cxt", "cct", "dcr", "dir", "exe" };
    Signatures = new[] { SignatureXFIR, SignatureRIFX, 0x00905A4Du, 0u };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    long base_offset = 0;
    if (file.View.AsciiEqual (0, "MZ"))
        base_offset = LookForXfir (file);
    uint signature = file.View.ReadUInt32 (base_offset);
    if (signature != SignatureXFIR && signature != SignatureRIFX)
        return null;
    using (var input = file.CreateStream())
    {
        ByteOrder ord = signature == SignatureXFIR ? ByteOrder.LittleEndian : ByteOrder.BigEndian;
        var reader = new Reader (input, ord);
        reader.Position = base_offset;
        var context = new SerializationContext();
        var dir_file = new DirectorFile();
        if (!dir_file.Deserialize (context, reader))
            return null;

        var dir = new List<Entry> ();
        if (dir_file.Codec != "APPL")
            ImportMedia (dir_file, dir);
        foreach (DirectorEntry entry in dir_file.Directory)
        {
            if (entry.Size != 0 && entry.Offset != -1 && RawChunks.Contains (entry.FourCC))
            {
                entry.Name = string.Format ("{0:D6}.{1}", entry.Id, entry.FourCC.Trim());
                if ("File" == entry.FourCC)
                {
                    entry.Offset -= 8;
                    entry.Size   += 8;
                }
                dir.Add (entry);
            }
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var snd = entry as SoundEntry;
    if (snd != null)
        return OpenSound (arc, snd);
    var pent = entry as PackedEntry;
    if (null == pent)
        return base.OpenEntry (arc, entry);
    var input = OpenChunkStream (arc.File, pent);
    var ment = entry as DirectorEntry;
    if (null == ment || !ConvertText || ment.FourCC != "STXT")
        return input.AsStream;
    using (input)
    {
        uint offset = Binary.BigEndian (input.ReadUInt32());
        uint length = Binary.BigEndian (input.ReadUInt32());
        input.Position = offset;
        var text = input.ReadBytes ((int)length);
        return new BinMemoryStream (text, entry.Name);
    }
}
```

#### OpenSound

```csharp
internal Stream OpenSound (ArcFile arc, SoundEntry entry) {
    if (null == entry.Header)
        return base.OpenEntry (arc, entry);
    var header = new byte[entry.Header.UnpackedSize];
    using (var input = OpenChunkStream (arc.File, entry.Header))
        input.Read (header, 0, header.Length);
    var format = entry.DeserializeHeader (header);
    var riff = new MemoryStream (0x2C);
    WaveAudio.WriteRiffHeader (riff, format, entry.Size);
    if (format.BitsPerSample < 16)
    {
        using (riff)
        {
            var input = OpenChunkStream (arc.File, entry).AsStream;
            return new PrefixStream (riff.ToArray(), input);
        }
    }

    var samples = new byte[entry.UnpackedSize];
    using (var input = OpenChunkStream (arc.File, entry))
        input.Read (samples, 0, samples.Length);
    for (int i = 1; i < samples.Length; i += 2)
    {
        byte s = samples[i-1];
        samples[i-1] = samples[i];
        samples[i] = s;
    }
    riff.Write (samples, 0, samples.Length);
    riff.Position = 0;
    return riff;
}
```

#### ImportMedia

```csharp
void ImportMedia (DirectorFile dir_file, List<Entry> dir) {
    var seen_ids = new HashSet<int>();
    foreach (var cast in dir_file.Casts)
    {
        foreach (var piece in cast.Members.Values)
        {
            if (seen_ids.Contains (piece.Id))
                continue;
            seen_ids.Add (piece.Id);
            Entry entry = null;
            if (piece.Type == DataType.Bitmap)
                entry = ImportBitmap (piece, dir_file, cast);
            else if (piece.Type == DataType.Sound)
                entry = ImportSound (piece, dir_file);
            if (entry != null && entry.Size > 0)
                dir.Add (entry);
        }
    }
}
```

#### ImportSound

```csharp
Entry ImportSound (CastMember sound, DirectorFile dir_file) {
    var name = sound.Info.Name;
    KeyTableEntry sndHrec = null, sndSrec = null;
    foreach (var elem in dir_file.KeyTable.Table.Where (e => e.CastId == sound.Id))
    {
        if ("ediM" == elem.FourCC)
        {
            var ediM = dir_file.Index[elem.Id];
            name = SanitizeName(name, ediM.Id);
            return new PackedEntry
            {
                Name = name + ".ediM",
                Type = "audio",
                Offset       = ediM.Offset,
                Size         = ediM.Size,
                UnpackedSize = ediM.UnpackedSize,
                IsPacked     = ediM.IsPacked
            };
        }
        else if ("snd " == elem.FourCC)
        {
            var snd = dir_file.Index[elem.Id];
            if (snd.Size != 0)
            {
                name = SanitizeName (name, snd.Id);
                return new PackedEntry
                {
                    Name = name + ".snd",
                    Type = "audio",
                    Offset = snd.Offset,
                    Size = snd.Size,
                    UnpackedSize = snd.Size,
                    IsPacked = false,
                };
            }
        }
        if (null == sndHrec && "sndH" == elem.FourCC)
            sndHrec = elem;
        else if (null == sndSrec && "sndS" == elem.FourCC)
            sndSrec = elem;
    }
    if (sndHrec == null || sndSrec == null)
        return null;
    var sndH = dir_file.Index[sndHrec.Id];
    var sndS = dir_file.Index[sndSrec.Id];
    name = SanitizeName (name, sndSrec.Id);
    return new SoundEntry
    {
        Name   = name + ".snd",
        Type   = "audio",
        Offset = sndS.Offset,
        Size   = sndS.Size,
        UnpackedSize = sndS.UnpackedSize,
        IsPacked = sndS.IsPacked,
        Header = sndH,
    };
}
```

#### ImportBitmap

```csharp
Entry ImportBitmap (CastMember bitmap, DirectorFile dir_file, Cast cast) {
    KeyTableEntry bitd = null, edim = null, alfa = null;
    foreach (var elem in dir_file.KeyTable.Table.Where (e => e.CastId == bitmap.Id))
    {
        if (null == bitd && "BITD" == elem.FourCC)
            bitd = elem;
        else if (null == edim && "ediM" == elem.FourCC)
            edim = elem;
        else if (null == alfa && "ALFA" == elem.FourCC)
            alfa = elem;
    }
    if (bitd == null && edim == null)
        return null;
    var entry = new BitmapEntry();
    if (bitd != null)
    {
        entry.DeserializeHeader (bitmap.SpecificData);
        var name = SanitizeName (bitmap.Info.Name, bitd.Id);
        var chunk = dir_file.Index[bitd.Id];
        entry.Name   = name + ".BITD";
        entry.Type   = "image";
        entry.Offset = chunk.Offset;
        entry.Size   = chunk.Size;
        entry.IsPacked = chunk.IsPacked;
        entry.UnpackedSize = chunk.UnpackedSize;
        if (entry.Palette > 0)
        {
            var cast_id = cast.Index[entry.Palette-1];
            var clut = dir_file.KeyTable.FindByCast (cast_id, "CLUT");
            if (clut != null)
                entry.PaletteRef = dir_file.Index[clut.Id];
        }
    }
    else
    {
        var name = SanitizeName (bitmap.Info.Name, edim.Id);
        var chunk = dir_file.Index[edim.Id];
        entry.Name   = name + ".jpg";
        entry.Type   = "image";
        entry.Offset = chunk.Offset;
        entry.Size   = chunk.Size;
        entry.IsPacked = false;
        entry.UnpackedSize = entry.Size;
    }
    if (alfa != null)
        entry.AlphaRef = dir_file.Index[alfa.Id];
    return entry;
}
```

#### SanitizeName

```csharp
string SanitizeName (string name, int id) {
    name = name?.Trim();
    if (string.IsNullOrEmpty (name))
        name = id.ToString ("D6");
    else
        name = ForbiddenCharsRe.Replace (name, "_");
    return name;
}
```

#### ReadAlphaChannel

```csharp
byte[] ReadAlphaChannel (ArcView file, DirectorEntry entry, ImageMetaData info) {
    using (var alpha = OpenChunkStream (file, entry))
    {
        var alpha_info = new BitdMetaData {
            Width = info.Width,
            Height = info.Height,
            BPP = 8,
            DepthType = 0x80,
        };
        var decoder = new BitdDecoder (alpha.AsStream, alpha_info, null);
        return decoder.Unpack8bpp();
    }
}
```

#### ReadPalette

```csharp
BitmapPalette ReadPalette (byte[] data) {
    int num_colors = data.Length / 6;
    var colors = new Color[num_colors];
    for (int i = 0; i < data.Length; i += 6)
    {
        colors[i/6] = Color.FromRgb (data[i], data[i+2], data[i+4]);
    }
    return new BitmapPalette (colors);
}
```

#### OpenChunkStream

```csharp
IBinaryStream OpenChunkStream (ArcView file, PackedEntry entry) {
    var input = file.CreateStream (entry.Offset, entry.Size);
    if (!entry.IsPacked)
        return input;
    var data = new byte[entry.UnpackedSize];
    using (var zstream = new ZLibStream (input, CompressionMode.Decompress))
        zstream.Read (data, 0, data.Length);
    return new BinMemoryStream (data, entry.Name);
}
```

#### LookForXfir

```csharp
long LookForXfir (ArcView file) {
    var exe = new ExeFile (file);
    long pos;
    if (exe.IsWin16)
    {
        pos = exe.FindString (exe.Overlay, s_xfir);
        if (pos < 0)
            return 0;
    }
    else
    {
        pos = exe.Overlay.Offset;
        if (pos >= file.MaxOffset)
            return 0;
        if (file.View.AsciiEqual (pos, "10JP") || file.View.AsciiEqual (pos, "59JP"))
        {
            pos = file.View.ReadUInt32 (pos+4);
        }
    }
    if (pos >= file.MaxOffset || !file.View.AsciiEqual (pos, "XFIR"))
        return 0;

    if (!file.View.AsciiEqual (pos+8, "LPPA"))
        return pos;
    var appl = new DirectorFile();
    var context = new SerializationContext();
    using (var input = file.CreateStream())
    {
        var reader = new Reader (input, ByteOrder.LittleEndian);
        input.Position = pos + 12;
        if (!appl.ReadMMap (context, reader))
            return 0;
        foreach (var entry in appl.Directory)
        {

            if (entry.FourCC == "File")
            {
                if (file.View.AsciiEqual (entry.Offset-8, "XFIR")
                    && !file.View.AsciiEqual (entry.Offset, "artX"))
                    return entry.Offset-8;
            }
        }
        return 0;
    }
}
```

### GameRes.Formats.Macromedia.BitmapEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte Flags ;

public byte DepthType ;

public int  Top ;

public int  Left ;

public int  Bottom ;

public int  Right ;

public int  BitDepth ;

public int  Palette ;

public DirectorEntry PaletteRef ;

public DirectorEntry AlphaRef ;
```

#### DeserializeHeader

```csharp
public void DeserializeHeader (byte[] data) {
    using (var input = new MemoryStream (data, false))
    {
        var reader = new Reader (input, ByteOrder.BigEndian);
        DepthType = reader.ReadU8();
        Flags  = reader.ReadU8();
        Top    = reader.ReadI16();
        Left   = reader.ReadI16();
        Bottom = reader.ReadI16();
        Right  = reader.ReadI16();
        if (data.Length > 0x16)
        {
            reader.Skip (0x0C);
            BitDepth = reader.ReadU16() & 0xFF;
            if (data.Length >= 0x1C)
            {
                reader.Skip (2);
                Palette = reader.ReadI16();
            }
        }
    }
}
```

### GameRes.Formats.Macromedia.SoundEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public DirectorEntry    Header ;
```

#### DeserializeHeader

```csharp
public WaveFormat DeserializeHeader (byte[] header) {

    return new WaveFormat {
        FormatTag             = 1,
        Channels              = (ushort)BigEndian.ToUInt32 (header, 0x4C),
        SamplesPerSecond      = BigEndian.ToUInt32 (header, 0x2C),
        AverageBytesPerSecond = BigEndian.ToUInt32 (header, 0x30),
        BlockAlign            = (ushort)BigEndian.ToUInt32 (header, 0x50),
        BitsPerSample         = (ushort)BigEndian.ToUInt32 (header, 0x44),
    };
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/Macromedia/DirectorFile.cs](DirectorFile.md)：本页引用的随包算法资料。
- [ArcFormats/Macromedia/ImageBITD.cs](ImageBITD.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Macromedia/ArcDXR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
