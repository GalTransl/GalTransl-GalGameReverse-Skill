# Valkyria / ArcODN：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ODN` / `GameRes.Formats.Valkyria.OdnOpener` | 未解析（不据此猜测） | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `OdnOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `OdnOpener.UnpackImage` | `ctl = input.ReadByte();` |
| `OdnOpener.UnpackImage` | `count = Binary.BigEndian (input.ReadUInt16());` |
| `OdnIndexReader.ReadIndex` | `if (m_entry_buf.AsciiEqual (8, "00000000"))` |
| `OdnIndexReader.ReadIndex` | `if (m_entry_buf.AsciiEqual (0x10, name))` |
| `OdnIndexReader.ReadIndex` | `else if (m_entry_buf.AsciiEqual (0x18, name))` |
| `OdnIndexReader.ReadV1` | `if (m_entry_buf.AsciiEqual (0, "END_ffffffffffff"))` |
| `OdnIndexReader.ReadV1` | `else if (m_entry_buf.AsciiEqual (0, "ffffffffffffffff"))` |
| `OdnIndexReader.ReadV1` | `else if (m_entry_buf.AsciiEqual (0, "HIME_END"))` |
| `OdnIndexReader.ReadV1` | `var entry = new OdnEntry { Name = name, Offset = Convert.ToUInt32 (offset, 16) };` |
| `OdnIndexReader.ReadV2` | `uint first_offset = Convert.ToUInt32 (first_offset_str, 16);` |
| `OdnIndexReader.ReadV2` | `var offset = Convert.ToUInt32 (offset_str, 16);` |
| `OdnIndexReader.ReadEncrypted` | `if (m_entry_buf.AsciiEqual (0, "ffffffffffffffff"))` |
| `OdnIndexReader.ReadEncrypted` | `var entry = new OdnEntry { Name = name, Offset = Convert.ToUInt32 (offset, 16) };` |
| `OdnIndexReader.FixupDir` | `var signature = m_file.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Valkyria.OdnEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public bool IsEncrypted ;
```

### GameRes.Formats.Valkyria.OdnOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static string[] RequiredExtensions = new[] { "odn", "dat", "pni" }

FixedSetSetting AudioSampleRate = new FixedSetSetting (Properties.Settings.Default) {
    Name = "ODNAudioSampleRate",
    Text = arcStrings.ODNAudioSampleRate,
    ValuesSet = new[] { 22050u, 44100u },
}

internal static readonly Regex Image24NameRe = new Regex ("^(?:back|phii|psss)") ;

internal static readonly Regex Image32NameRe = new Regex ("^(?:data|codn|cccc|fund|puni|wind)") ;

internal static readonly Regex ScriptNameRe  = new Regex ("^(?:scrp|menu|sysm)") ;

internal static readonly Regex AudioNameRe   = new Regex ("^hime") ;

static readonly Size[] ImageDimensions = new Size[] {
    new Size (1024, 768),
    new Size (1024, 512),
    new Size (800, 600),
    new Size (640, 480),
    new Size (512, 512),
    new Size (400, 600),
    new Size (400, 200),
}
```

#### OdnOpener

```csharp
public OdnOpener () {
    Settings = new[] { AudioSampleRate };
    Extensions = RequiredExtensions;
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasAnyOfExtensions (RequiredExtensions))
        return null;
    var reader = new OdnIndexReader (file);
    var dir = reader.ReadIndex();
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var oent = entry as OdnEntry;
    if (oent != null && oent.IsEncrypted)
    {
        byte key = (byte)~entry.Offset;
        var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
        Decrypt (data, data.Length, key);
        return new BinMemoryStream (data);
    }
    if (AudioNameRe.IsMatch (entry.Name))
    {
        using (var wav = new MemoryStream (0x2C))
        {
            var format = new WaveFormat {
                FormatTag = 1,
                Channels = 1,
                SamplesPerSecond = AudioSampleRate.Get<uint>(),
                BlockAlign = 2,
                BitsPerSample = 16,
            };
            format.SetBPS();
            WaveAudio.WriteRiffHeader (wav, format, entry.Size);
            var header = wav.ToArray();
            var data = arc.File.CreateStream (entry.Offset, entry.Size);
            return new PrefixStream (header, data);
        }
    }
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (0x5E6A6A42 == input.Signature)
    {
        return new XoredStream (input, 0xD);
    }
    return input;
}
```

#### Decrypt

```csharp
internal static byte Decrypt (byte[] data, int size, byte key) {
    for (int i = 0; i < size; ++i)
        data[i] ^= key--;
    return key;
}
```

#### UnpackImage

```csharp
void UnpackImage (IBinaryStream input, Stream output, int pixel_size) {
    var max_output_size = ImageDimensions[0].Width * ImageDimensions[0].Height * pixel_size;
    var pixel = new byte[pixel_size];
    int ctl = 1;
    for (;;)
    {
        if (1 == ctl)
        {
            ctl = input.ReadByte();
            if (-1 == ctl)
                break;
            ctl |= 0x100;
        }
        if (pixel.Length != input.Read (pixel, 0, pixel.Length))
            break;
        int count = 0;
        if (0 != (ctl & 1))
            count = Binary.BigEndian (input.ReadUInt16());
        for (int i = 0; i <= count; ++i)
            output.Write (pixel, 0, pixel.Length);
        if (output.Length > max_output_size)
            throw new InvalidFormatException();
        ctl >>= 1;
    }
    output.Position = 0;
}
```

### GameRes.Formats.Valkyria.OdnIndexReader

#### 状态与常量

```csharp
ArcView     m_file ;

byte[]      m_entry_buf = new byte[0x20] ;

List<Entry> m_dir = new List<Entry>() ;

Encoding    m_enc ;

bool        m_scripts_encrypted = true ;
```

#### OdnIndexReader

```csharp
public OdnIndexReader (ArcView file) {
    m_file = file;
    m_enc = Encoding.ASCII.WithFatalFallback();
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex () {
    m_file.View.Read (0, m_entry_buf, 0, 0x1C);
    if (m_entry_buf.AsciiEqual (8, "00000000"))
    {
        ReadV1();
    }
    else if (m_entry_buf.IsAsciiVisible (0, 0x10))
    {
        var name = m_enc.GetString (m_entry_buf, 0, 4);
        if (m_entry_buf.AsciiEqual (0x10, name))
            ReadV2 (0x10);
        else if (m_entry_buf.AsciiEqual (0x18, name))
            ReadV2 (0x18);
    }
    else
    {
        var key = OdnOpener.Decrypt (m_entry_buf, 0x10, 0xFF);
        if (m_entry_buf.AsciiEqual (8, "00000000"))
            ReadEncrypted (key);
    }
    if (0 == m_dir.Count)
        return null;
    FixupDir();
    return m_dir;
}
```

#### ReadV1

```csharp
void ReadV1 () {
    uint index_offset = 0;
    for (;;)
    {
        if (0x10 != m_file.View.Read (index_offset, m_entry_buf, 0, 0x10))
            throw new InvalidFormatException();
        index_offset += 0x10;
        if (m_entry_buf.AsciiEqual (0, "END_ffffffffffff"))
            break;
        else if (m_entry_buf.AsciiEqual (0, "ffffffffffffffff"))
        {
            m_scripts_encrypted = false;
            break;
        }
        else if (m_entry_buf.AsciiEqual (0, "HIME_END"))
        {
            index_offset += 8;
            break;
        }
        var name = m_enc.GetString (m_entry_buf, 0, 8);
        var offset = m_enc.GetString (m_entry_buf, 8, 8);
        var entry = new OdnEntry { Name = name, Offset = Convert.ToUInt32 (offset, 16) };
        m_dir.Add (entry);
    }
    foreach (OdnEntry entry in m_dir)
        entry.Offset += index_offset;
    if (m_dir.Any() && m_dir[m_dir.Count-1].Offset == m_file.MaxOffset)
        m_dir.RemoveAt (m_dir.Count-1);
}
```

#### ReadV2

```csharp
void ReadV2 (uint record_size) {
    uint index_offset = 0;
    var first_offset_str = m_enc.GetString (m_entry_buf, 8, 8);
    uint first_offset = Convert.ToUInt32 (first_offset_str, 16);
    while (index_offset < first_offset)
    {
        var offset_str = m_enc.GetString (m_entry_buf, 8, 8);
        var offset = Convert.ToUInt32 (offset_str, 16);
        if (m_file.MaxOffset == offset)
            break;
        var name = m_enc.GetString (m_entry_buf, 0, 8);
        var entry = new OdnEntry { Name = name, Offset = offset };
        m_dir.Add (entry);
        index_offset += record_size;
        if (record_size != m_file.View.Read (index_offset, m_entry_buf, 0, record_size))
            throw new InvalidFormatException();
    }
}
```

#### ReadEncrypted

```csharp
void ReadEncrypted (byte key) {
    uint index_offset = 0;
    for (;;)
    {
        index_offset += 0x10;
        if (m_entry_buf.AsciiEqual (0, "ffffffffffffffff"))
            break;
        var name = m_enc.GetString (m_entry_buf, 0, 8);
        var offset = m_enc.GetString (m_entry_buf, 8, 8);
        var entry = new OdnEntry { Name = name, Offset = Convert.ToUInt32 (offset, 16) };
        m_dir.Add (entry);
        if (0x10 != m_file.View.Read (index_offset, m_entry_buf, 0, 0x10))
            throw new InvalidFormatException();
        key = OdnOpener.Decrypt (m_entry_buf, 0x10, key);
    }
    foreach (var entry in m_dir)
        entry.Offset += index_offset;
}
```

#### FixupDir

```csharp
void FixupDir () {
    for (int i = 0; i < m_dir.Count; ++i)
    {
        var entry = (OdnEntry)m_dir[i];

        long next_offset = i+1 < m_dir.Count ? m_dir[i+1].Offset : m_file.MaxOffset;
        entry.Size = (uint)(next_offset - entry.Offset);

        if (OdnOpener.Image24NameRe.IsMatch (entry.Name))
        {
            entry.Type = "image";
        }
        else if (OdnOpener.ScriptNameRe.IsMatch (entry.Name))
        {
            entry.Type = "script";
            entry.IsEncrypted = m_scripts_encrypted;
        }
        else if (OdnOpener.AudioNameRe.IsMatch (entry.Name))
        {
            entry.Type = "audio";
        }
        else if (entry.Size > 4)
        {
            var signature = m_file.View.ReadUInt32 (entry.Offset);
            IResource res = null;
            if (0x5E6A6A42 == signature)
                res = OggAudio.Instance;
            else if (AudioFormat.Wav.Signature == signature)
                res = AudioFormat.Wav;
            else
                res = AutoEntry.DetectFileType (signature);
            if (res != null)
                entry.ChangeType (res);
            else if (OdnOpener.Image32NameRe.IsMatch (entry.Name))
                entry.Type = "image";
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/AudioOGG.cs](../AudioOGG.md)：本页引用的随包算法资料。
- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Valkyria/ArcODN.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
