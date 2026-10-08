# Macromedia / ArcSWF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SWF` / `GameRes.Formats.Macromedia.SwfOpener` | `swf` | `43575308`, `46575308` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SwfOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "CWS") &&` |
| `SwfOpener.TryOpen` | `!file.View.AsciiEqual (0, "FWS"))` |
| `SwfOpener.TryOpen` | `bool is_compressed = file.View.ReadByte (0) == 'C';` |
| `SwfOpener.TryOpen` | `int version = file.View.ReadByte (3);` |
| `SwfChunk.Id` | `public int     Id { get { return Data.Length > 2 ? Data.ToUInt16 (0) : -1; } }` |
| `SwfReader.Parse` | `m_frame_rate = m_input.ReadUInt16();` |
| `SwfReader.Parse` | `m_frame_count = m_input.ReadUInt16();` |
| `SwfReader.ReadChunk` | `int length = m_buffer.ToUInt16 (0);` |
| `SwfReader.ReadChunk` | `length = m_input.ReadInt32();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum Types : short
    {
        End                 = 0,
        ShowFrame           = 1,
        DefineShape         = 2,
        DefineBitsJpeg      = 6,
        JpegTables          = 8,
        DefineText          = 11,
        DoAction            = 12,
        DefineSound         = 14,
        SoundStreamHead     = 18,
        SoundStreamBlock    = 19,
        DefineBitsLossless  = 20,
        DefineBitsJpeg2     = 21,
        DefineShape2        = 22,
        DefineShape3        = 32,
        DefineText2         = 33,
        DefineBitsJpeg3     = 35,
        DefineBitsLossless2 = 36,
        DefineSprite        = 39,
        SoundStreamHead2    = 45,
        ExportAssets        = 56,
        DefineVideoStream   = 60,
        VideoFrame          = 61,
        FileAttributes      = 69,
        Font3               = 75,
        DefineBinary        = 87,
    }
```

### GameRes.Formats.Macromedia.SwfEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public SwfChunk     Chunk ;
```

### GameRes.Formats.Macromedia.SwfSoundEntry

继承/接口：`SwfEntry`。

#### 状态与常量

```csharp
public readonly List<SwfChunk>  SoundStream = new List<SwfChunk>() ;
```

### GameRes.Formats.Macromedia.SwfOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static Dictionary<Types, Extractor> ExtractMap = new Dictionary<Types, Extractor> {

    { Types.DefineBitsJpeg,      ExtractChunkContents },
    { Types.DefineBitsLossless,  ExtractChunk },
    { Types.DefineBitsLossless2, ExtractChunk },
    { Types.DefineSound,         ExtractAudio },
    { Types.SoundStreamHead,     ExtractSoundStream },
    { Types.SoundStreamHead2,    ExtractSoundStream },
}

static Dictionary<Types, string> TypeMap = new Dictionary<Types, string> {
    { Types.DefineBitsJpeg,         "image" },
    { Types.DefineBitsJpeg2,        "image" },
    { Types.DefineBitsJpeg3,        "image" },
    { Types.DefineBitsLossless,     "image" },
    { Types.DefineBitsLossless2,    "image" },
    { Types.DefineSound,            "audio" },
    { Types.DoAction,               "" },

    { Types.JpegTables,             "JpegTables" },

}
```

#### SwfOpener

```csharp
public SwfOpener () {
    Signatures = new uint[] { 0x08535743, 0x08535746, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "CWS") &&
        !file.View.AsciiEqual (0, "FWS"))
        return null;
    bool is_compressed = file.View.ReadByte (0) == 'C';
    int version = file.View.ReadByte (3);
    using (var reader = new SwfReader (file.CreateStream(), version, is_compressed))
    {
        var chunks = reader.Parse();
        var base_name = Path.GetFileNameWithoutExtension (file.Name);
        var dir = chunks.Where (t => t.Length > 2 && TypeMap.ContainsKey (t.Type))
            .Select (t => new SwfEntry {
                Name = string.Format ("{0}#{1:D5}", base_name, t.Id),
                Type = GetTypeFromId (t.Type),
                Chunk = t,
                Offset = 0,
                Size = (uint)t.Length
            } as Entry).ToList();
        SwfSoundEntry current_stream = null;
        foreach (var chunk in chunks.Where (t => IsSoundStream (t)))
        {
            switch (chunk.Type)
            {
            case Types.SoundStreamHead:
            case Types.SoundStreamHead2:
                if ((chunk.Data[1] & 0x30) != 0x20)
                {
                    current_stream = null;
                    continue;
                }
                current_stream = new SwfSoundEntry {
                    Name = string.Format ("{0}#{1:D5}", base_name, chunk.Id),
                    Type = "audio",
                    Chunk = chunk,
                    Offset = 0,
                };
                dir.Add (current_stream);
                break;

            case Types.SoundStreamBlock:
                if (current_stream != null)
                {
                    current_stream.Size += (uint)(chunk.Data.Length - 4);
                    current_stream.SoundStream.Add (chunk);
                }
                break;
            }
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var swent = (SwfEntry)entry;
    Extractor extract;
    if (!ExtractMap.TryGetValue (swent.Chunk.Type, out extract))
        extract = ExtractChunk;
    return extract (swent);
}
```

#### GetTypeFromId

```csharp
static string GetTypeFromId (Types type_id) {
    string type;
    if (TypeMap.TryGetValue (type_id, out type))
        return type;
    return type_id.ToString();
}
```

#### ExtractChunk

```csharp
static Stream ExtractChunk (SwfEntry entry) {
    return new BinMemoryStream (entry.Chunk.Data);
}
```

#### ExtractChunkContents

```csharp
static Stream ExtractChunkContents (SwfEntry entry) {
    var source = entry.Chunk;
    return new BinMemoryStream (source.Data, 2, source.Length-2);
}
```

#### ExtractSoundStream

```csharp
static Stream ExtractSoundStream (SwfEntry entry) {
    var swe = (SwfSoundEntry)entry;
    var output = new MemoryStream ((int)swe.Size);
    foreach (var chunk in swe.SoundStream)
        output.Write (chunk.Data, 4, chunk.Data.Length-4);
    output.Position = 0;
    return output;
}
```

#### ExtractAudio

```csharp
static Stream ExtractAudio (SwfEntry entry) {
    var chunk = entry.Chunk;
    int flags = chunk.Data[2];
    int format = flags >> 4;
    if (2 == format)
        return new BinMemoryStream (chunk.Data, 9, chunk.Length-9);
    int sample_rate = (flags >> 2) & 3;
    int bits_per_sample = (flags & 2) != 0 ? 16 : 8;
    int channels = (flags & 1) + 1;

    return new BinMemoryStream (chunk.Data, 2, chunk.Length-2);
}
```

#### Extractor

```csharp
delegate Stream Extractor (SwfEntry entry) ;
```

#### IsSoundStream

```csharp
internal static bool IsSoundStream (SwfChunk chunk) {
    return chunk.Type == Types.SoundStreamHead
        || chunk.Type == Types.SoundStreamHead2
        || chunk.Type == Types.SoundStreamBlock;
}
```

### GameRes.Formats.Macromedia.SwfChunk

#### 状态与常量

```csharp
public Types    Type ;

public byte[]   Data ;

public int Length { get { return Data.Length; } }

public int     Id { get { return Data.Length > 2 ? Data.ToUInt16 (0) : -1; } }
```

#### SwfChunk

```csharp
public SwfChunk (Types id, int length) {
    Type = id;
    Data = length > 0 ? new byte[length] : Array.Empty<byte>();
}
```

### GameRes.Formats.Macromedia.SwfReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

MsbBitStream    m_bits ;

int             m_version ;

Int32Rect       m_dim ;

int     m_frame_rate ;

int     m_frame_count ;

List<SwfChunk>  m_chunks = new List<SwfChunk>() ;

byte[]  m_buffer = new byte[4] ;

bool m_disposed = false ;
```

#### SwfReader

```csharp
public SwfReader (IBinaryStream input, int version, bool is_compressed) {
    m_input = input;
    m_version = version;
    m_input.Position = 8;
    if (is_compressed)
    {
        var zstream = new ZLibStream (input.AsStream, CompressionMode.Decompress);
        m_input = new BinaryStream (zstream, m_input.Name);
    }
    m_bits = new MsbBitStream (m_input.AsStream, true);
}
```

#### Parse

```csharp
public List<SwfChunk> Parse () {
    ReadDimensions();
    m_bits.Reset();
    m_frame_rate = m_input.ReadUInt16();
    m_frame_count = m_input.ReadUInt16();
    for (;;)
    {
        var chunk = ReadChunk();
        if (null == chunk)
            break;
        m_chunks.Add (chunk);
    }
    return m_chunks;
}
```

#### ReadDimensions

```csharp
void ReadDimensions () {
    int rsize = m_bits.GetBits (5);
    m_dim.X = GetSignedBits (rsize);
    m_dim.Width = GetSignedBits (rsize) - m_dim.X;
    m_dim.Y = GetSignedBits (rsize);
    m_dim.Height = GetSignedBits (rsize) - m_dim.Y;
}
```

#### ReadChunk

```csharp
SwfChunk ReadChunk () {
    if (m_input.Read (m_buffer, 0, 2) != 2)
        return null;
    int length = m_buffer.ToUInt16 (0);
    Types id = (Types)(length >> 6);
    length &= 0x3F;
    if (0x3F == length)
        length = m_input.ReadInt32();
    if (Types.DefineSprite == id)
        length = 4;
    var chunk = new SwfChunk (id, length);
    if (length > 0)
    {
        if (m_input.Read (chunk.Data, 0, length) < length)
            return null;
    }
    return chunk;
}
```

#### GetSignedBits

```csharp
int GetSignedBits (int count) {
    int v = m_bits.GetBits (count);
    if ((v >> (count - 1)) != 0)
        v |= -1 << count;
    return v;
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Macromedia/ArcSWF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
