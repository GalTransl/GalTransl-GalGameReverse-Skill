# Entis / ImageERI：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `EriFile.ReadSection` | `section.Length = this.ReadInt64();` |
| `EriFile.FindSection` | `var length = this.ReadInt64();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum CvType
    {
        Lossless_EMI =  0x03010000,
        Lossless_ERI =  0x03020000,
        DCT_ERI      =  0x00000001,
        LOT_ERI      =  0x00000005,
        LOT_ERI_MSS  =  0x00000105,
    }

enum EriCode
    {
        ArithmeticCode      = 32,
        RunlengthGamma      = -1,
        RunlengthHuffman    = -4,
        Nemesis             = -16,
    }

enum EriType
    {
        RGB         = 0x00000001,
        Gray        = 0x00000002,
        BGR         = 0x00000003,
        YUV         = 0x00000004,
        HSB         = 0x00000006,
        RGBA        = 0x04000001,
        BGRA        = 0x04000003,
        Mask        = 0x0000FFFF,
        WithPalette = 0x01000000,
        UseClipping = 0x02000000,
        WithAlpha   = 0x04000000,
        SideBySide  = 0x10000000,
    }

enum EriSampling
    {
        YUV_4_4_4 = 0x00040404,
        YUV_4_2_2 = 0x00040202,
        YUV_4_1_1 = 0x00040101,
    }
```

### GameRes.Formats.Entis.EriMetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public int      StreamPos ;

public int      Version ;

public CvType   Transformation ;

public EriCode  Architecture ;

public EriType FormatType ;

public bool     VerticalFlip ;

public int      ClippedPixel ;

public EriSampling SamplingFlags ;

public ulong    QuantumizedBits ;

public ulong    AllottedBits ;

public int      BlockingDegree ;

public int      LappedBlock ;

public int      FrameTransform ;

public int      FrameDegree ;

public EriFileHeader Header ;
```

### GameRes.Formats.Entis.EriFileHeader

#### 状态与常量

```csharp
public int      Version ;

public int      ContainedFlag ;

public int      KeyFrameCount ;

public int      FrameCount ;

public int      AllFrameTime ;
```

### GameRes.Formats.Entis.EriFile

继承/接口：`BinaryReader`。

#### ReadSection

```csharp
public Section ReadSection () {
    var section = new Section();
    section.Id = new AsciiString (8);
    if (8 != this.Read (section.Id.Value, 0, 8))
        throw new EndOfStreamException();
    section.Length = this.ReadInt64();
    return section;
}
```

#### FindSection

```csharp
public long FindSection (string name) {
    var id = new AsciiString (8);
    for (;;)
    {
        if (8 != this.Read (id.Value, 0, 8))
            throw new EndOfStreamException();
        var length = this.ReadInt64();
        if (length < 0)
            throw new EndOfStreamException();
        if (id == name)
            return length;
        this.BaseStream.Seek (length, SeekOrigin.Current);
    }
}
```

### GameRes.Formats.Entis.EriFile.Section

#### 状态与常量

```csharp
public AsciiString  Id ;

public long         Length ;
```

### GameRes.Formats.Entis.EriFormat

继承/接口：`ImageFormat`。

#### 状态与常量

```csharp
static readonly Regex s_TagRe = new Regex (@"^\s*#\s*(\S+)") ;
```

#### EriFormat

```csharp
public EriFormat () {
    Extensions = new [] { "eri", "emi" };
    Signatures = new uint[] { 0x69746E45, 0x54534956 };
}
```

#### ReadPalette

```csharp
internal static Color[] ReadPalette (Stream input, int palette_length) {
    int colors = palette_length / 4;
    if (colors <= 0 || colors > 0x100)
        throw new InvalidFormatException();
    return ImageFormat.ReadColorMap (input, colors);
}
```

#### ReadImageData

```csharp
internal EriReader ReadImageData (IBinaryStream stream, EriMetaData meta) {
    stream.Position = meta.StreamPos;
    Color[] palette = null;
    using (var input = new EriFile (stream.AsStream))
    {
        for (;;)
        {
            var section = input.ReadSection();
            if ("Stream  " == section.Id)
                continue;
            if ("ImageFrm" == section.Id)
                break;
            if ("Palette " == section.Id && meta.BPP <= 8 && section.Length <= 0x400)
            {
                palette = ReadPalette (stream.AsStream, (int)section.Length);
                continue;
            }
            input.BaseStream.Seek (section.Length, SeekOrigin.Current);
        }
    }
    var reader = new EriReader (stream.AsStream, meta, palette);
    reader.DecodeImage();

    if (!string.IsNullOrEmpty (meta.Description))
    {
        var tags = ParseTagInfo (meta.Description);
        string ref_file;
        if (tags.TryGetValue ("reference-file", out ref_file))
        {
            ref_file = ref_file.TrimEnd (null);
            if (!string.IsNullOrEmpty (ref_file))
            {
                if ((meta.BPP + 7) / 8 < 3)
                    throw new InvalidFormatException();

                ref_file = VFS.CombinePath (VFS.GetDirectoryName (meta.FileName), ref_file);
                using (var ref_src = VFS.OpenBinaryStream (ref_file))
                {
                    var ref_info = ReadMetaData (ref_src) as EriMetaData;
                    if (null == ref_info)
                        throw new FileNotFoundException ("Referenced image not found", ref_file);
                    ref_info.FileName = ref_file;
                    var ref_reader = ReadImageData (ref_src, ref_info);
                    reader.AddImageBuffer (ref_reader);
                }
            }
        }
    }
    return reader;
}
```

#### ParseTagInfo

```csharp
Dictionary<string, string> ParseTagInfo (string desc) {
    var dict = new Dictionary<string, string>();
    if (string.IsNullOrEmpty (desc))
    {
        return dict;
    }
    if ('#' != desc[0])
    {
        dict["comment"] = desc;
        return dict;
    }
    var tag_value = new StringBuilder();
    using (var reader = new StringReader (desc))
    {
        string line = reader.ReadLine();
        while (null != line)
        {
            var match = s_TagRe.Match (line);
            if (!match.Success)
                break;
            string tag = match.Groups[1].Value;

            tag_value.Clear();
            for (;;)
            {
                line = reader.ReadLine();
                if (null == line)
                    break;
                if (line.StartsWith ("#"))
                {
                    if (line.Length < 2 || '#' != line[1])
                        break;
                    line = line.Substring (1);
                }
                tag_value.AppendLine (line);
            }
            dict[tag] = tag_value.ToString();
        }
    }
    return dict;
}
```

## 配套算法与外部条件

- [ArcFormats/Entis/EriReader.cs](EriReader.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Entis/ImageERI.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
