# KiriKiri / ArcXP3：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `XP3` / `GameRes.Formats.KiriKiri.Xp3Opener` | `xp3`, `exe` | `5850330d`, `4d5a9000` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Xp3Opener.TryOpen` | `if (0x5a4d == file.View.ReadUInt16 (0))` |
| `Xp3Opener.TryOpen` | `long dir_offset = base_offset + file.View.ReadInt64 (base_offset+0x0b);` |
| `Xp3Opener.TryOpen` | `if (0x80 == file.View.ReadUInt32 (dir_offset))` |
| `Xp3Opener.TryOpen` | `dir_offset = base_offset + file.View.ReadInt64 (dir_offset+9);` |
| `Xp3Opener.TryOpen` | `int header_type = file.View.ReadByte (dir_offset);` |
| `Xp3Opener.TryOpen` | `long header_size = file.View.ReadInt64 (dir_offset+1);` |
| `Xp3Opener.TryOpen` | `long packed_size = file.View.ReadInt64 (dir_offset+1);` |
| `Xp3Opener.TryOpen` | `long header_size = file.View.ReadInt64 (dir_offset+9);` |
| `Xp3Opener.TryOpen` | `uint entry_signature = header.ReadUInt32();` |
| `Xp3Opener.TryOpen` | `long entry_size = header.ReadInt64();` |
| `Xp3Opener.TryOpen` | `uint section = header.ReadUInt32();` |
| `Xp3Opener.TryOpen` | `long section_size = header.ReadInt64();` |
| `Xp3Opener.TryOpen` | `entry.IsEncrypted = 0 != header.ReadUInt32();` |
| `Xp3Opener.TryOpen` | `long file_size = header.ReadInt64();` |
| `Xp3Opener.TryOpen` | `long packed_size = header.ReadInt64();` |
| `Xp3Opener.TryOpen` | `bool compressed  = 0 != header.ReadInt32();` |
| `Xp3Opener.TryOpen` | `long segment_offset = base_offset+header.ReadInt64();` |
| `Xp3Opener.TryOpen` | `long segment_size   = header.ReadInt64();` |
| `Xp3Opener.TryOpen` | `long segment_packed_size = header.ReadInt64();` |
| `Xp3Opener.TryOpen` | `entry.Hash = header.ReadUInt32();` |
| `Xp3Opener.TryOpen` | `long offset = header.ReadInt64() + base_offset;` |
| `Xp3Opener.TryOpen` | `header.ReadUInt32();` |
| `Xp3Opener.TryOpen` | `uint size = header.ReadUInt32();` |
| `Xp3Opener.TryOpen` | `var yuz = file.View.ReadBytes (offset, size);` |
| `Xp3Opener.TryOpen` | `var offset = header.ReadInt64 () + base_offset;` |
| `Xp3Opener.TryOpen` | `var size = header.ReadUInt32 ();` |
| `Xp3Opener.TryOpen` | `var flags = header.ReadUInt16 ();` |
| `Xp3Opener.TryOpen` | `var hx = file.View.ReadBytes (offset, size);` |
| `Xp3Opener.TryOpen` | `uint hash = header.ReadUInt32();` |
| `Xp3Opener.TryOpen` | `int name_size = header.ReadInt16();` |
| `Xp3Opener.SkipExeHeader` | `if (offset != -1 && 0 != file.View.ReadUInt32 (offset+signature.Length))` |
| `Xp3Opener.SkipExeHeader` | `if (0 != file.View.ReadUInt32 (offset+signature.Length))` |
| `Xp3Stream.ReadByte` | `public override int ReadByte () {` |
| `Xp3Stream.ReadByte` | `b = m_stream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KiriKiri.Xp3Segment

#### 状态与常量

```csharp
public bool IsCompressed ;

public long Offset ;

public uint Size ;

public uint PackedSize ;
```

### GameRes.Formats.KiriKiri.Xp3Entry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
List<Xp3Segment> m_segments = new List<Xp3Segment>() ;

public bool          IsEncrypted { get; set; }

public ICrypt             Cipher { get; set; }

public List<Xp3Segment> Segments { get { return m_segments; } }

public uint                 Hash { get; set; }

public object              Extra { get; set; }
```

### GameRes.Formats.KiriKiri.Xp3Options

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public int              Version { get; set; }

public bool       CompressIndex { get; set; }

public bool    CompressContents { get; set; }

public bool          RetainDirs { get; set; }
```

### GameRes.Formats.KiriKiri.Xp3Scheme

继承/接口：`ResourceScheme`。

#### 状态与常量

```csharp
public ISet<string>                 NoCryptTitles ;
```

### GameRes.Formats.KiriKiri.Xp3Opener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] s_xp3_header = {
    (byte)'X', (byte)'P', (byte)'3', 0x0d, 0x0a, 0x20, 0x0a, 0x1a, 0x8b, 0x67, 0x01
}

public bool ForceEncryptionQuery = true ;

internal static readonly ICrypt NoCryptAlgorithm = new NoCrypt() ;

static readonly Regex ObfuscatedPathRe = new Regex (@"[^\\/]+[\\/]\.\.[\\/]") ;

static Xp3Scheme KiriKiriScheme = new Xp3Scheme {
    KnownSchemes = new Dictionary<string, ICrypt>(),
    NoCryptTitles = new HashSet<string>()
}

public static ISet<string> NoCryptTitles {
    get { return KiriKiriScheme.NoCryptTitles; }
}
```

#### Xp3Opener

```csharp
public Xp3Opener () {
    Signatures = new uint[] { 0x0d335058, 0x00905A4D, 0 };
    Extensions = new[] { "xp3", "exe" };
    ContainedFormats = new[] { "TLG", "BMP", "PNG", "JPEG", "OGG", "WAV", "TXT" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
            long base_offset = 0;
            if (0x5a4d == file.View.ReadUInt16 (0))
                base_offset = SkipExeHeader (file, s_xp3_header);
            if (!file.View.BytesEqual (base_offset, s_xp3_header))
                return null;
            long dir_offset = base_offset + file.View.ReadInt64 (base_offset+0x0b);
            if (dir_offset < 0x13 || dir_offset >= file.MaxOffset)
                return null;
            if (0x80 == file.View.ReadUInt32 (dir_offset))
            {
                dir_offset = base_offset + file.View.ReadInt64 (dir_offset+9);
                if (dir_offset < 0x13 || dir_offset >= file.MaxOffset)
                    return null;
            }
            int header_type = file.View.ReadByte (dir_offset);
            if (0 != header_type && 1 != header_type)
                return null;

            Stream header_stream;
            if (0 == header_type)
            {
                long header_size = file.View.ReadInt64 (dir_offset+1);
                if (header_size > uint.MaxValue)
                    return null;
                header_stream = file.CreateStream (dir_offset+9, (uint)header_size);
            }
            else
            {
                long packed_size = file.View.ReadInt64 (dir_offset+1);
                if (packed_size > uint.MaxValue)
                    return null;
                long header_size = file.View.ReadInt64 (dir_offset+9);
                using (var input = file.CreateStream (dir_offset+17, (uint)packed_size))
                    header_stream = ZLibCompressor.DeCompress (input);
            }

            var crypt_algorithm = new Lazy<ICrypt> (() => QueryCryptAlgorithm (file), false);

            var dir = new List<Entry>();
            dir_offset = 0;
            using (var header = new BinaryReader (header_stream, Encoding.Unicode))
            using (var filename_map = new FilenameMap())
            {
                Dictionary<string, HxEntry> hx_entry_info = null;
                while (-1 != header.PeekChar())
                {
                    uint entry_signature = header.ReadUInt32();
                    long entry_size = header.ReadInt64();
                    if (entry_size < 0)
                        return null;
                    dir_offset += 12 + entry_size;
                    if (0x656C6946 == entry_signature)
                    {
                        var entry = new Xp3Entry();
                        while (entry_size > 0)
                        {
                            uint section = header.ReadUInt32();
                            long section_size = header.ReadInt64();
                            entry_size -= 12;
                            if (section_size > entry_size)
                            {

                                if (section != 0x6f666e69)
                                    break;
                                section_size = entry_size;
                            }
                            entry_size -= section_size;
                            long next_section_pos = header.BaseStream.Position + section_size;
                            switch (section)
                            {
                            case 0x6f666e69:
                                if (entry.Size != 0 || !string.IsNullOrEmpty (entry.Name))
                                {
                                    goto NextEntry;
                                }
                                entry.IsEncrypted = 0 != header.ReadUInt32();
                                long file_size = header.ReadInt64();
                                long packed_size = header.ReadInt64();
                                if (file_size >= uint.MaxValue || packed_size > uint.MaxValue || packed_size > file.MaxOffset)
                                {
                                    goto NextEntry;
                                }
                                entry.IsPacked     = file_size != packed_size;
                                entry.Size         = (uint)packed_size;
                                entry.UnpackedSize = (uint)file_size;

                                if (entry.IsEncrypted || ForceEncryptionQuery)
                                    entry.Cipher = crypt_algorithm.Value;
                                else
                                    entry.Cipher = NoCryptAlgorithm;

                                var name = entry.Cipher.ReadName (header);
                                if (null == name)
                                {
                                    goto NextEntry;
                                }
                                if (entry.Cipher.ObfuscatedIndex && ObfuscatedPathRe.IsMatch (name))
                                {
                                    goto NextEntry;
                                }
                                if (filename_map.Count > 0)
                                    name = filename_map.Get (entry.Hash, name);
                                if (name.Length > 0x100)
                                {
                                    goto NextEntry;
                                }
                                entry.Name = name;
                                entry.IsEncrypted = !(entry.Cipher is NoCrypt)
                                    && !(entry.Cipher.StartupTjsNotEncrypted && "startup.tjs" == name);
                                break;
                            case 0x6d676573:
                                int segment_count = (int)(section_size / 0x1c);
                                if (segment_count > 0)
                                {
                                    for (int i = 0; i < segment_count; ++i)
                                    {
                                        bool compressed  = 0 != header.ReadInt32();
                                        long segment_offset = base_offset+header.ReadInt64();
                                        long segment_size   = header.ReadInt64();
                                        long segment_packed_size = header.ReadInt64();
                                        if (segment_offset > file.MaxOffset || segment_packed_size > file.MaxOffset)
                                        {
                                            goto NextEntry;
                                        }
                                        var segment = new Xp3Segment {
                                            IsCompressed = compressed,
                                            Offset       = segment_offset,
                                            Size         = (uint)segment_size,
                                            PackedSize   = (uint)segment_packed_size
                                        };
                                        entry.Segments.Add (segment);
                                    }
                                    entry.Offset = entry.Segments.First().Offset;
                                }
                                break;
                            case 0x726c6461:
                                if (4 == section_size)
                                    entry.Hash = header.ReadUInt32();
                                break;

                            default:
                                break;
                            }
                            header.BaseStream.Position = next_section_pos;
                        }
                        if (!string.IsNullOrEmpty (entry.Name) && entry.Segments.Any())
                        {
                            if (entry.Cipher.ObfuscatedIndex)
                            {
                                DeobfuscateEntry (entry);
                            }
                            if (null != hx_entry_info)
                            {
                                if (hx_entry_info.TryGetValue (entry.Name, out HxEntry info))
                                {
                                    entry.Extra = info;

                                    var sb = new StringBuilder ();
                                    if (!string.IsNullOrEmpty (info.Path))
                                    {
                                        sb.Append (info.Path);
                                        if (!info.Path.EndsWith ("/") && !info.Path.EndsWith ("\\"))
                                            sb.Append ('/');
                                    }
                                    if (!string.IsNullOrEmpty (info.Name))
                                    {
                                        sb.Append (info.Name);
                                        if (sb.Length > 0)
                                            entry.Name = sb.ToString ();
                                    }
                                    else
                                    {
                                        sb.Append (entry.Name);
                                        if (sb.Length > 0)
                                            entry.Name = sb.ToString ();
                                    }
                                }
                            }
                            entry.Type = FormatCatalog.Instance.GetTypeFromName(entry.Name, ContainedFormats);
                            dir.Add (entry);
                        }
                    }
                    else if (0x3A == (entry_signature >> 24))
                    {
                        if (entry_size >= 0x10 && crypt_algorithm.Value is SenrenCxCrypt)
                        {
                            long offset = header.ReadInt64() + base_offset;
                            header.ReadUInt32();
                            uint size = header.ReadUInt32();
                            if (offset > 0 && offset + size <= file.MaxOffset)
                            {
                                var yuz = file.View.ReadBytes (offset, size);
                                var crypt = crypt_algorithm.Value as SenrenCxCrypt;
                                crypt.ReadYuzNames (yuz, filename_map);
                            }
                        }
                    }
                    else if (0x34767848 == entry_signature)
                    {
                        if (crypt_algorithm.Value is HxCrypt)
                        {
                            try
                            {
                                var offset = header.ReadInt64 () + base_offset;
                                var size = header.ReadUInt32 ();
                                var flags = header.ReadUInt16 ();
                                var hx = file.View.ReadBytes (offset, size);
                                var crypt = crypt_algorithm.Value as HxCrypt;
                                hx_entry_info = crypt.ReadIndex (Path.GetFileName (file.Name), hx);
                            }
                            catch (Exception) {  }
                        }
                    }
                    else if (entry_size > 7)
                    {

                        uint hash = header.ReadUInt32();
                        int name_size = header.ReadInt16();
                        if (name_size > 0)
                        {
                            entry_size -= 6;
                            if (name_size * 2 <= entry_size)
                            {
                                var filename = new string (header.ReadChars (name_size));
                                filename_map.Add (hash, filename);
                            }
                        }
                    }
NextEntry:
                    header.BaseStream.Position = dir_offset;
                }
            }
            if (0 == dir.Count)
                return null;
            var arc = new ArcFile (file, this, dir);
            try
            {
                if (crypt_algorithm.IsValueCreated)
                    crypt_algorithm.Value.Init (arc);
                return arc;
            }
            catch
            {
                arc.Dispose();
                throw;
            }
        }
```

#### DeobfuscateEntry

```csharp
private static void DeobfuscateEntry (Xp3Entry entry) {
    if (entry.Segments.Count > 1)
        entry.Segments.RemoveRange (1, entry.Segments.Count-1);
    entry.IsPacked = entry.Segments[0].IsCompressed;
    entry.Size = entry.Segments[0].PackedSize;
    entry.UnpackedSize = entry.Segments[0].Size;
}
```

#### SkipExeHeader

```csharp
internal static long SkipExeHeader (ArcView file, byte[] signature) {
    var exe = new ExeFile (file);
    if (exe.ContainsSection (".rsrc"))
    {
        var offset = exe.FindString (exe.Sections[".rsrc"], signature);
        if (offset != -1 && 0 != file.View.ReadUInt32 (offset+signature.Length))
            return offset;
    }
    var section = exe.Overlay;
    while (section.Offset < file.MaxOffset)
    {
        var offset = exe.FindString (section, signature, 0x10);
        if (-1 == offset)
            break;
        if (0 != file.View.ReadUInt32 (offset+signature.Length))
            return offset;
        section.Offset = offset + 0x10;
        section.Size = (uint)(file.MaxOffset - section.Offset);
    }
    return 0;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var xp3_entry = entry as Xp3Entry;
    if (null == xp3_entry)
        return arc.File.CreateStream (entry.Offset, entry.Size);

    Stream input;
    if (1 == xp3_entry.Segments.Count && !xp3_entry.IsEncrypted)
    {
        var segment = xp3_entry.Segments.First();
        if (segment.IsCompressed)
            input = new ZLibStream (arc.File.CreateStream (segment.Offset, segment.PackedSize),
                                   CompressionMode.Decompress);
        else
            input = arc.File.CreateStream (segment.Offset, segment.Size);
    }
    else
        input = new Xp3Stream (arc.File, xp3_entry);

    return xp3_entry.Cipher.EntryReadFilter (xp3_entry, input);
}
```

#### QueryCryptAlgorithm

```csharp
ICrypt QueryCryptAlgorithm (ArcView file) {
    var alg = GuessCryptAlgorithm (file);
    if (null != alg)
        return alg;
    var options = Query<Xp3Options> (arcStrings.XP3EncryptedNotice);
    return options.Scheme;
}
```

#### GetScheme

```csharp
public static ICrypt GetScheme (string scheme) {
    ICrypt algorithm;
    if (string.IsNullOrEmpty (scheme) || !KnownSchemes.TryGetValue (scheme, out algorithm))
        algorithm = NoCryptAlgorithm;
    return algorithm;
}
```

#### GetFileCheckSum

```csharp
static uint GetFileCheckSum (Stream src) {

    var sum = new Adler32();
    byte[] buf = new byte[64*1024];
    for (;;)
    {
        int read = src.Read (buf, 0, buf.Length);
        if (0 == read) break;
        sum.Update (buf, 0, read);
    }
    return sum.Value;
}
```

#### RawFileCopy

```csharp
void RawFileCopy (FileStream file, Xp3Entry xp3entry, Stream output, bool compress) {
    if (file.Length > uint.MaxValue)
        throw new FileSizeException();

    uint unpacked_size    = (uint)file.Length;
    xp3entry.UnpackedSize = (uint)unpacked_size;
    xp3entry.Size         = (uint)unpacked_size;
    compress = compress && unpacked_size > 0;
    var segment = new Xp3Segment {
        IsCompressed = compress,
        Offset       = output.Position,
        Size         = unpacked_size,
        PackedSize   = unpacked_size
    };
    if (compress)
    {
        var start = output.Position;
        using (var zstream = new ZLibStream (output, CompressionMode.Compress, CompressionLevel.Level9, true))
        {
            xp3entry.Hash = CheckedCopy (file, zstream);
        }
        segment.PackedSize = (uint)(output.Position - start);
        xp3entry.Size = segment.PackedSize;
    }
    else
    {
        xp3entry.Hash = CheckedCopy (file, output);
    }
    xp3entry.Segments.Add (segment);
}
```

#### EncryptedFileCopy

```csharp
void EncryptedFileCopy (FileStream file, Xp3Entry xp3entry, Stream output, bool compress) {
    if (file.Length > int.MaxValue)
        throw new FileSizeException();

    using (var map = MemoryMappedFile.CreateFromFile (file, null, 0,
            MemoryMappedFileAccess.Read, null, HandleInheritability.None, true))
    {
        uint unpacked_size    = (uint)file.Length;
        xp3entry.UnpackedSize = (uint)unpacked_size;
        xp3entry.Size         = (uint)unpacked_size;
        using (var view = map.CreateViewAccessor (0, unpacked_size, MemoryMappedFileAccess.Read))
        {
            var segment = new Xp3Segment {
                IsCompressed = compress,
                Offset       = output.Position,
                Size         = unpacked_size,
                PackedSize   = unpacked_size,
            };
            if (compress)
            {
                output = new ZLibStream (output, CompressionMode.Compress, CompressionLevel.Level9, true);
            }
            unsafe
            {
                byte[] read_buffer = new byte[81920];
                byte* ptr = view.GetPointer (0);
                try
                {
                    var checksum = new Adler32();
                    bool hash_after_crypt = xp3entry.Cipher.HashAfterCrypt;
                    if (!hash_after_crypt)
                        xp3entry.Hash = checksum.Update (ptr, (int)unpacked_size);
                    int offset = 0;
                    int remaining = (int)unpacked_size;
                    while (remaining > 0)
                    {
                        int amount = Math.Min (remaining, read_buffer.Length);
                        remaining -= amount;
                        Marshal.Copy ((IntPtr)(ptr+offset), read_buffer, 0, amount);
                        xp3entry.Cipher.Encrypt (xp3entry, offset, read_buffer, 0, amount);
                        if (hash_after_crypt)
                            checksum.Update (read_buffer, 0, amount);
                        output.Write (read_buffer, 0, amount);
                        offset += amount;
                    }
                    if (hash_after_crypt)
                        xp3entry.Hash = checksum.Value;
                }
                finally
                {
                    view.SafeMemoryMappedViewHandle.ReleasePointer();
                    if (compress)
                    {
                        var dest = (output as ZLibStream).BaseStream;
                        output.Dispose();
                        segment.PackedSize = (uint)(dest.Position - segment.Offset);
                        xp3entry.Size = segment.PackedSize;
                    }
                    xp3entry.Segments.Add (segment);
                }
            }
        }
    }
}
```

#### CheckedCopy

```csharp
uint CheckedCopy (Stream src, Stream dst) {
    var checksum = new Adler32();
    var read_buffer = new byte[81920];
    for (;;)
    {
        int read = src.Read (read_buffer, 0, read_buffer.Length);
        if (0 == read)
            break;
        checksum.Update (read_buffer, 0, read);
        dst.Write (read_buffer, 0, read);
    }
    return checksum.Value;
}
```

#### ShouldCompressFile

```csharp
bool ShouldCompressFile (Entry entry) {
    if ("image" == entry.Type || "archive" == entry.Type)
        return false;
    if (entry.Name.HasExtension (".ogg"))
        return false;
    return true;
}
```

#### GuessCryptAlgorithm

```csharp
ICrypt GuessCryptAlgorithm (ArcView file) {
    var title = FormatCatalog.Instance.LookupGame (file.Name);
    if (string.IsNullOrEmpty (title))
        title = FormatCatalog.Instance.LookupGame (file.Name, @"..\*.exe");
    if (string.IsNullOrEmpty (title))
        return null;
    ICrypt algorithm;
    if (!KnownSchemes.TryGetValue (title, out algorithm) && NoCryptTitles.Contains (title))
        algorithm = NoCryptAlgorithm;
    return algorithm;
}
```

### GameRes.Formats.KiriKiri.Xp3Stream

继承/接口：`Stream`。

#### 状态与常量

```csharp
ArcView     m_file ;

Xp3Entry    m_entry ;

IEnumerator<Xp3Segment> m_segment ;

Stream      m_stream ;

long        m_offset = 0 ;

bool        m_eof = false ;

public override bool CanRead { get { return !disposed; } }

public override bool CanSeek { get { return false; } }

public override long Length { get { return m_entry.UnpackedSize; } }

public override long Position {
    get { return m_offset; }
    set { throw new NotSupportedException ("Xp3Stream.Position not supported."); }
}

bool disposed = false ;
```

#### Xp3Stream

```csharp
public Xp3Stream (ArcView file, Xp3Entry entry) {
    m_file = file;
    m_entry = entry;
    m_segment = entry.Segments.GetEnumerator();
    NextSegment();
}
```

#### NextSegment

```csharp
private void NextSegment () {
    if (!m_segment.MoveNext())
    {
        m_eof = true;
        return;
    }
    if (null != m_stream)
        m_stream.Dispose();
    var segment = m_segment.Current;
    var segment_size = segment.IsCompressed ? segment.PackedSize : segment.Size;
    m_stream = m_file.CreateStream (segment.Offset, segment_size);
    if (segment.IsCompressed)
        m_stream = new ZLibStream (m_stream, CompressionMode.Decompress);
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int total = 0;
    while (!m_eof && count > 0)
    {
        int read = m_stream.Read (buffer, offset, count);
        if (0 != read)
        {
            if (m_entry.IsEncrypted)
                m_entry.Cipher.Decrypt (m_entry, m_offset, buffer, offset, read);
            m_offset += read;
            total += read;
            offset += read;
            count -= read;
        }
        if (0 != count)
            NextSegment();
    }
    return total;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int b = -1;
    while (!m_eof)
    {
        b = m_stream.ReadByte();
        if (-1 != b)
        {
            if (m_entry.IsEncrypted)
                b = m_entry.Cipher.Decrypt (m_entry, m_offset++, (byte)b);
            break;
        }
        NextSegment();
    }
    return b;
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    throw new NotSupportedException ("Xp3Stream.Seek method is not supported");
}
```

#### SetLength

```csharp
public override void SetLength (long length) {
    throw new NotSupportedException ("Xp3Stream.SetLength method is not supported");
}
```

#### WriteByte

```csharp
public override void WriteByte (byte value) {
    throw new NotSupportedException("Xp3Stream.WriteByte method is not supported");
}
```

### GameRes.Formats.KiriKiri.FilenameMap

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
Dictionary<uint, string>    m_hash_map = new Dictionary<uint, string>() ;

Dictionary<string, string>  m_md5_map = new Dictionary<string, string>() ;

MD5             m_md5 = MD5.Create() ;

StringBuilder   m_md5_str = new StringBuilder() ;

public int Count { get { return m_md5_map.Count; } }

bool _disposed = false ;
```

#### Add

```csharp
public void Add (uint hash, string filename) {
    if (!m_hash_map.ContainsKey (hash))
        m_hash_map[hash] = filename;

    m_md5_map[GetMd5Hash (filename)] = filename;
}
```

#### AddShortcut

```csharp
public void AddShortcut (string shortcut, string filename) {
    m_md5_map[shortcut] = filename;
}
```

#### Get

```csharp
public string Get (uint hash, string md5) {
    string filename;
    if (m_md5_map.TryGetValue (md5, out filename))
        return filename;
    if (m_hash_map.TryGetValue (hash, out filename))
        return filename;
    return md5;
}
```

#### GetMd5Hash

```csharp
string GetMd5Hash (string text) {
    var text_bytes = Encoding.Unicode.GetBytes (text.ToLowerInvariant());
    var md5 = m_md5.ComputeHash (text_bytes);
    m_md5_str.Clear();
    for (int i = 0; i < md5.Length; ++i)
        m_md5_str.AppendFormat ("{0:x2}", md5[i]);
    return m_md5_str.ToString();
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/KiriKiri/CryptAlgorithms.cs](CryptAlgorithms.md)：本页引用的随包算法资料。
- [ArcFormats/KiriKiri/HxCrypt.cs](HxCrypt.md)：本页引用的随包算法资料。
- [ArcFormats/KiriKiri/YuzCrypt.cs](YuzCrypt.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/KiriKiri/ArcXP3.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
