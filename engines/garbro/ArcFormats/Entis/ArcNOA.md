# Entis / ArcNOA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `NOA` / `GameRes.Formats.Entis.NoaOpener` | `noa`, `dat`, `rsa`, `arc`, `emc` | `456e7469`, `56495354` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `NoaOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "Entis\x1a") && !file.View.AsciiEqual (0, "VIST\x1a"))` |
| `NoaOpener.TryOpen` | `uint id = file.View.ReadUInt32 (8);` |
| `NoaOpener.TryOpen` | `bool old_format = file.View.AsciiEqual (0x10, "EMSAC-Binary Archive");` |
| `NoaOpener.OpenEntry` | `ulong size = arc.File.View.ReadUInt64 (entry.Offset+8);` |
| `NoaOpener.OpenEntry` | `return DecodeSimpleCrypt32 (input, narc.Password, BitConverter.ToUInt32 (nent.Extra, 4));` |
| `IndexReader.ParseDirEntry` | `if (!m_file.View.AsciiEqual (dir_offset, "DirEntry"))` |
| `IndexReader.ParseDirEntry` | `long size = m_file.View.ReadInt64 (dir_offset+8);` |
| `IndexReader.ParseDirEntry` | `int count = m_file.View.ReadInt32 (dir_offset);` |
| `IndexReader.ParseDirEntry` | `entry.Size = m_file.View.ReadUInt32 (dir_offset);` |
| `IndexReader.ParseDirEntry` | `entry.Attr = m_file.View.ReadUInt32 (dir_offset);` |
| `IndexReader.ParseDirEntry` | `entry.Encryption = m_file.View.ReadUInt32 (dir_offset);` |
| `IndexReader.ParseDirEntry` | `entry.Offset = base_offset + m_file.View.ReadInt64 (dir_offset);` |
| `IndexReader.ParseDirEntry` | `uint extra_length = m_file.View.ReadUInt32 (dir_offset);` |
| `IndexReader.ParseDirEntry` | `entry.Extra = m_file.View.ReadBytes (dir_offset, extra_length);` |
| `IndexReader.ParseDirEntry` | `uint name_length = m_file.View.ReadUInt32 (dir_offset);` |
| `IndexReader.ParseDirEntry` | `string name = m_file.View.ReadString (dir_offset, name_length, Encoding);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Entis.NoaOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public string PassPhrase { get; set; }
```

### GameRes.Formats.Entis.NoaEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte[]   Extra ;

public uint     Encryption ;

public uint     Attr ;
```

### GameRes.Formats.Entis.NoaArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public string Password ;
```

#### NoaArchive

```csharp
public NoaArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, string password = null)
    : base (arc, impl, dir) {
    Password = password;
}
```

### GameRes.Formats.Entis.NoaOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
EncodingSetting NoaEncoding = new EncodingSetting ("NOAEncodingCP", "DefaultEncoding") ;
```

#### NoaOpener

```csharp
public NoaOpener () {
    Extensions = new string[] { "noa", "dat", "rsa", "arc", "emc" };
    Signatures = new uint[] { 0x69746E45, 0x54534956 };
    Settings = new[] { NoaEncoding };
    ContainedFormats = new[] { "ERI", "EMI", "MIO", "EMS", "TXT" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "Entis\x1a") && !file.View.AsciiEqual (0, "VIST\x1a"))
        return null;
    uint id = file.View.ReadUInt32 (8);
    if (0x02000400 != id)
        return null;
    bool old_format = file.View.AsciiEqual (0x10, "EMSAC-Binary Archive");
    Encoding enc = old_format ? Encodings.cp932 : NoaEncoding.Get<Encoding>();
    var reader = new IndexReader (file, enc);
    if (!reader.ParseRoot() || 0 == reader.Dir.Count)
        return null;
    if (reader.HasEncrypted)
    {
        var password = GetArcPassword (file.Name);
        if (!string.IsNullOrEmpty (password))
            return new NoaArchive (file, this, reader.Dir, password);
    }
    return new ArcFile (file, this, reader.Dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var nent = entry as NoaEntry;
    if (null == nent)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    ulong size = arc.File.View.ReadUInt64 (entry.Offset+8);
    if (size > int.MaxValue)
        throw new FileSizeException();
    if (size <= 4)
        return Stream.Null;

    if (EncType.ERISACode == nent.Encryption)
    {
        var enc = arc.File.CreateStream (entry.Offset+0x10, (uint)size-4);
        return new ErisaNemesisStream (enc, (int)entry.Size);
    }

    var narc = arc as NoaArchive;
    var input = arc.File.CreateStream (entry.Offset+0x10, (uint)size);
    if (EncType.Raw == nent.Encryption || null == narc || null == narc.Password)
        return input;

    if (EncType.SimpleCrypt32 == nent.Encryption)
    {
        if (0 != size % 4)
            throw new InvalidFormatException ();

        using (input)
            return DecodeSimpleCrypt32 (input, narc.Password, BitConverter.ToUInt32 (nent.Extra, 4));
    }

    if (EncType.BSHFCrypt == nent.Encryption)
    {
        using (input)
            return DecodeBSHF (input, narc.Password);
    }
    if (EncType.ERISACrypt == nent.Encryption)
    {
        Stream enc;
        using (input)
            enc = DecodeBSHF (input, narc.Password);
        return new ErisaNemesisStream (enc, (int)entry.Size);
    }
    Trace.WriteLine (string.Format ("{0}: encryption scheme 0x{1:x8} not implemented",
                                    nent.Name, nent.Encryption));
    return input;
}
```

#### GetArcPassword

```csharp
string GetArcPassword (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name, @"..\*.exe");
    string password = null;
    if (string.IsNullOrEmpty (title) || !KnownKeys.ContainsKey (title))
    {
        password = ExtractNoaPassword (arc_name);
        if (password != null)
            return password;
        var options = Query<NoaOptions> (arcStrings.ArcEncryptedNotice);
        if (!string.IsNullOrEmpty (options.PassPhrase))
        {
            return options.PassPhrase;
        }
        title = options.Scheme;
    }
    if (!string.IsNullOrEmpty (title))
    {
        Dictionary<string, string> filemap;
        if (KnownKeys.TryGetValue (title, out filemap))
        {
            var filename = Path.GetFileName (arc_name).ToLowerInvariant();
            filemap.TryGetValue (filename, out password);
        }
    }
    return password;
}
```

#### ExtractNoaPassword

```csharp
string ExtractNoaPassword (string arc_name) {
    if (VFS.IsVirtual)
        return null;
    var dir = VFS.GetDirectoryName (arc_name);
    var noa_name = Path.GetFileName (arc_name);
    var parent_dir = Directory.GetParent (dir).FullName;
    var exe_files = VFS.GetFiles (VFS.CombinePath (parent_dir, "*.exe")).Concat (VFS.GetFiles (VFS.CombinePath (dir, "*.exe")));
    foreach (var exe_entry in exe_files)
    {
        try
        {
            using (var exe = new ExeFile.ResourceAccessor (exe_entry.Name))
            {
                var cotomi = exe.GetResource ("IDR_COTOMI", "#10");
                if (null == cotomi)
                    continue;
                using (var res = new MemoryStream (cotomi))
                using (var input = new ErisaNemesisStream (res))
                {
                    var xml = new XmlDocument();
                    xml.Load (input);
                    var password = XmlFindArchiveKey (xml, noa_name);
                    if (password != null)
                    {
                        Trace.WriteLine (string.Format ("{0}: found password \"{1}\"", noa_name, password), "[NOA]");
                        return password;
                    }
                }
            }
        }
        catch {  }
    }
    return null;
}
```

#### XmlFindArchiveKey

```csharp
string XmlFindArchiveKey (XmlDocument xml, string filename) {
    foreach (XmlNode archive in xml.DocumentElement.SelectNodes ("archive[@path and @key]"))
    {
        var attr = archive.Attributes;
        var path = attr["path"].Value;
        if (VFS.IsPathEqualsToFileName (path, filename))
            return attr["key"].Value;
    }
    return null;
}
```

#### DecodeBSHF

```csharp
Stream DecodeBSHF (Stream input, string password) {
    uint nTotalBytes = (uint)input.Length - 4;
    var pBSHF = new BSHFDecodeContext (0x10000);
    pBSHF.AttachInputFile (input);
    pBSHF.PrepareToDecodeBSHFCode (password);

    byte[] buf = new byte[nTotalBytes];
    uint decoded = pBSHF.DecodeBSHFCodeBytes (buf, nTotalBytes);
    if (decoded < nTotalBytes)
        throw new EndOfStreamException ("Unexpected end of encrypted stream");

    return new MemoryStream (buf);
}
```

#### DecodeSimpleCrypt32

```csharp
Stream DecodeSimpleCrypt32(Stream input, string password, uint imul_key) {
    var xor_key_map = Encoding.UTF8.GetBytes (password);
    imul_key ^= Crc32.Compute (xor_key_map, 0, xor_key_map.Length);

    for (int i = 0; i < xor_key_map.Length; i++)
    {
        var key_byte   = (byte)~xor_key_map[i];
        xor_key_map[i] = (byte)(key_byte ^ (key_byte * 7));
    }

    var buffer = new byte[input.Length];
    input.Read(buffer, 0, (int)input.Length);

    var buffer_span  = MemoryMarshal.Cast<byte, uint> (buffer);
    var xor_key_span = MemoryMarshal.Cast<byte, uint> (xor_key_map);

    for (int i = 0; i < buffer_span.Length; i += xor_key_span.Length)
    {
        var window_size = Math.Min (buffer_span.Length - i, xor_key_span.Length);
        var window_span = buffer_span.Slice (i, window_size);

        for (int j = 0; j < window_size; j++)
        {
            window_span[j] = (window_span[j] * imul_key) ^ xor_key_span[j];
        }
    }

    return new MemoryStream (buffer);
}
```

### GameRes.Formats.Entis.NoaOpener.EncType

#### 状态与常量

```csharp
public const uint Raw           = 0x00000000 ;

public const uint ERISACode     = 0x80000010 ;

public const uint BSHFCrypt     = 0x40000000 ;

public const uint SimpleCrypt32 = 0x20000000 ;

public const uint ERISACrypt    = 0xC0000010 ;

public const uint ERISACrypt32  = 0xA0000010 ;
```

### GameRes.Formats.Entis.NoaOpener.IndexReader

#### 状态与常量

```csharp
ArcView     m_file ;

List<Entry> m_dir = new List<Entry>() ;

bool        m_found_encrypted = false ;

const char PathSeparatorChar = '/' ;

public List<Entry> Dir { get { return m_dir; } }

public bool HasEncrypted { get { return m_found_encrypted; } }

public Encoding Encoding { get; set; }
```

#### IndexReader

```csharp
public IndexReader (ArcView file, Encoding enc) {
    m_file = file;
    Encoding = enc;
}
```

#### ParseRoot

```csharp
public bool ParseRoot () {
    return ParseDirEntry (0x40, "");
}
```

#### ParseDirEntry

```csharp
private bool ParseDirEntry (long dir_offset, string cur_dir) {
    if (!m_file.View.AsciiEqual (dir_offset, "DirEntry"))
        return false;
    long size = m_file.View.ReadInt64 (dir_offset+8);
    if (size <= 0 || size > int.MaxValue)
        return false;
    if ((uint)size > m_file.View.Reserve (dir_offset+8, (uint)size))
        return false;
    long base_offset = dir_offset;
    dir_offset += 0x10;
    int count = m_file.View.ReadInt32 (dir_offset);
    dir_offset += 4;
    if (m_dir.Capacity < m_dir.Count+count)
        m_dir.Capacity = m_dir.Count+count;
    for (int i = 0; i < count; ++i)
    {
        var entry = new NoaEntry();
        entry.Size = m_file.View.ReadUInt32 (dir_offset);
        dir_offset += 8;

        entry.Attr = m_file.View.ReadUInt32 (dir_offset);
        dir_offset += 4;

        entry.Encryption = m_file.View.ReadUInt32 (dir_offset);
        m_found_encrypted = m_found_encrypted || (EncType.Raw != entry.Encryption && EncType.ERISACode != entry.Encryption);
        bool is_packed = EncType.ERISACode == entry.Encryption || EncType.ERISACrypt == entry.Encryption;
        dir_offset += 4;

        entry.Offset = base_offset + m_file.View.ReadInt64 (dir_offset);
        if (!is_packed && !entry.CheckPlacement (m_file.MaxOffset))
        {
            entry.Size = (uint)(m_file.MaxOffset - entry.Offset);
        }
        dir_offset += 0x10;

        uint extra_length = m_file.View.ReadUInt32 (dir_offset);
        dir_offset += 4;
        if (extra_length > 0 && 0 == (entry.Attr & 0x70))
        {
            entry.Extra = m_file.View.ReadBytes (dir_offset, extra_length);
            if (entry.Extra.Length != extra_length)
                return false;
        }
        dir_offset += extra_length;
        uint name_length = m_file.View.ReadUInt32 (dir_offset);
        dir_offset += 4;

        string name = m_file.View.ReadString (dir_offset, name_length, Encoding);
        dir_offset += name_length;

        if (string.IsNullOrEmpty (cur_dir))
            entry.Name = name;
        else
            entry.Name = cur_dir + PathSeparatorChar + name;
        entry.Type = FormatCatalog.Instance.GetTypeFromName (name);
        if (0x10 == entry.Attr)
        {
            if (!ParseDirEntry (entry.Offset+0x10, entry.Name))
                return false;
        }
        else if (0x20 == entry.Attr || 0x40 == entry.Attr)
        {
            break;
        }
        else
        {
            m_dir.Add (entry);
        }
    }
    return true;
}
```

### GameRes.Formats.Entis.ERISADecodeContext

#### 状态与常量

```csharp
protected int       m_nIntBufCount ;

protected uint      m_dwIntBuffer ;

protected uint      m_nBufferingSize ;

protected uint      m_nBufCount ;

protected byte[]    m_ptrBuffer ;

protected int       m_ptrNextBuf ;

protected Stream    m_pFile ;

protected ERISADecodeContext m_pContext ;
```

#### ERISADecodeContext

```csharp
public ERISADecodeContext (uint nBufferingSize) {
    m_nIntBufCount = 0;
    m_nBufferingSize = (nBufferingSize + 0x03) & ~0x03u;
    m_nBufCount = 0;
    m_ptrBuffer = new byte[nBufferingSize];
    m_pFile = null;
    m_pContext = null;
}
```

#### AttachInputFile

```csharp
public void AttachInputFile (Stream file) {
    m_pFile = file;
    m_pContext = null;
}
```

#### AttachInputContext

```csharp
public void AttachInputContext (ERISADecodeContext context) {
    m_pFile = null;
    m_pContext = context;
}
```

#### ReadNextData

```csharp
public uint ReadNextData (byte[] ptrBuffer, uint nBytes) {
    if (m_pFile != null)
    {
        return (uint)m_pFile.Read (ptrBuffer, 0, (int)nBytes);
    }
    else if (m_pContext != null)
    {
        return m_pContext.DecodeBytes (ptrBuffer, nBytes);
    }
    else
    {
        throw new ApplicationException ("Uninitialized ERISA encryption context");
    }
}
```

#### DecodeBytes

```csharp
public abstract uint DecodeBytes (Array ptrDst, uint nCount) ;
```

#### PrefetchBuffer

```csharp
protected bool PrefetchBuffer() {
    if (0 == m_nIntBufCount)
    {
        if (0 == m_nBufCount)
        {
            m_ptrNextBuf = 0;
            m_nBufCount = ReadNextData (m_ptrBuffer, m_nBufferingSize);
            if (0 == m_nBufCount)
            {
                return false;
            }
            if (0 != (m_nBufCount & 0x03))
            {
                uint    i = m_nBufCount;
                m_nBufCount += 4 - (m_nBufCount & 0x03);
                while (i < m_nBufCount)
                    m_ptrBuffer[i ++] = 0;
            }
        }
        m_nIntBufCount = 32;
        m_dwIntBuffer =
              ((uint)m_ptrBuffer[m_ptrNextBuf] << 24) | ((uint)m_ptrBuffer[m_ptrNextBuf+1] << 16)
            | ((uint)m_ptrBuffer[m_ptrNextBuf+2] << 8) | (uint)m_ptrBuffer[m_ptrNextBuf+3];
        m_ptrNextBuf += 4;
        m_nBufCount -= 4;
    }
    return true;
}
```

#### FlushBuffer

```csharp
public void FlushBuffer () {
    m_nIntBufCount = 0;
    m_nBufCount = 0;
}
```

#### GetABit

```csharp
public int GetABit () {
    if (!PrefetchBuffer())
    {
        return  1;
    }
    int nValue = ((int)m_dwIntBuffer) >> 31;
    --m_nIntBufCount;
    m_dwIntBuffer <<= 1;
    return nValue;
}
```

#### GetNBits

```csharp
public uint GetNBits (int n) {
    uint nCode = 0;
    while (n != 0)
    {
        if (!PrefetchBuffer())
            break;

        int nCopyBits = Math.Min (n, m_nIntBufCount);
        nCode = (nCode << nCopyBits) | (m_dwIntBuffer >> (32 - nCopyBits));
        n -= nCopyBits;
        m_nIntBufCount -= nCopyBits;
        m_dwIntBuffer <<= nCopyBits;
    }
    return nCode;
}
```

### GameRes.Formats.Entis.BSHFDecodeContext

继承/接口：`ERISADecodeContext`。

#### 状态与常量

```csharp
ERIBshfBuffer   m_pBshfBuf ;

uint            m_dwBufPos ;
```

#### BSHFDecodeContext

```csharp
public BSHFDecodeContext (uint nBufferingSize) : base (nBufferingSize) {
    m_pBshfBuf = null;
}
```

#### PrepareToDecodeBSHFCode

```csharp
public void PrepareToDecodeBSHFCode (string pszPassword) {
    if (null == m_pBshfBuf)
    {
        m_pBshfBuf = new ERIBshfBuffer();
    }
    if (string.IsNullOrEmpty (pszPassword))
    {
        pszPassword = " ";
    }
    int char_count = Encoding.ASCII.GetByteCount (pszPassword);
    int length = Math.Max (char_count, 32);
    var pass_bytes = new byte[length];
    char_count = Encoding.ASCII.GetBytes (pszPassword, 0, pszPassword.Length, pass_bytes, 0);
    if (char_count < 32)
    {
        pass_bytes[char_count++] = 0x1b;
        for (int i = char_count; i < 32; ++i)
        {
            pass_bytes[i] = (byte)(pass_bytes[i % char_count] + pass_bytes[i - 1]);
        }
    }
    m_pBshfBuf.m_strPassword = pass_bytes;
    m_pBshfBuf.m_dwPassOffset = 0;
    m_dwBufPos = 32;
}
```

#### DecodeBytes

```csharp
public override uint DecodeBytes (Array ptrDst, uint nCount) {
    return DecodeBSHFCodeBytes (ptrDst as byte[], nCount);
}
```

#### DecodeBSHFCodeBytes

```csharp
public uint DecodeBSHFCodeBytes (byte[] ptrDst, uint nCount) {
    uint nDecoded = 0;
    while (nDecoded < nCount)
    {
        if (m_dwBufPos >= 32)
        {
            for (int i = 0; i < 32; ++i)
            {
                if (0 == m_nBufCount)
                {
                    m_ptrNextBuf = 0;
                    m_nBufCount = ReadNextData (m_ptrBuffer, m_nBufferingSize);
                    if (0 == m_nBufCount)
                    {
                        return nDecoded;
                    }
                }
                m_pBshfBuf.m_srcBSHF[i] = m_ptrBuffer[m_ptrNextBuf++];
                m_nBufCount--;
            }
            m_pBshfBuf.DecodeBuffer();
            m_dwBufPos = 0;
        }
        ptrDst[nDecoded++] = m_pBshfBuf.m_bufBSHF[m_dwBufPos++];
    }
    return nDecoded;
}
```

### GameRes.Formats.Entis.ERIBshfBuffer

#### 状态与常量

```csharp
public byte[]   m_strPassword ;

public uint     m_dwPassOffset = 0 ;

public byte[]   m_bufBSHF = new byte[32] ;

public byte[]   m_srcBSHF = new byte[32] ;

public byte[]   m_maskBSHF = new byte[32] ;
```

#### DecodeBuffer

```csharp
public void DecodeBuffer () {
    int nPassLen = m_strPassword.Length;
    if ((int)m_dwPassOffset >= nPassLen)
    {
        m_dwPassOffset = 0;
    }
    for (int i = 0; i < 32; ++i)
    {
        m_bufBSHF[i]  = 0;
        m_maskBSHF[i] = 0;
    }
    int iPos = (int) m_dwPassOffset++;
    int iBit = 0;
    for (int i = 0; i < 256; ++i)
    {
        iBit = (iBit + m_strPassword[iPos++]) & 0xFF;
        if (iPos >= nPassLen)
        {
            iPos = 0;
        }
        int iOffset = (iBit >> 3);
        int iMask = (0x80 >> (iBit & 0x07));
        while (0xFF == m_maskBSHF[iOffset])
        {
            iBit = (iBit + 8) & 0xFF;
            iOffset = (iBit >> 3);
        }
        while (0 != (m_maskBSHF[iOffset] & iMask))
        {
            iBit ++;
            iMask >>= 1;
            if (0 == iMask)
            {
                iBit = (iBit + 8) & 0xFF;
                iOffset = (iBit >> 3);
                iMask = 0x80;
            }
        }
        Debug.Assert (iMask != 0);
        m_maskBSHF[iOffset] |= (byte) iMask;

        if (0 != (m_srcBSHF[(i >> 3)] & (0x80 >> (i & 0x07))))
        {
            m_bufBSHF[iOffset] |= (byte)iMask;
        }
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Entis/ErisaNemesis.cs](ErisaNemesis.md)：本页引用的随包算法资料。
- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/ResourceSettings.cs](../ResourceSettings.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Entis/ArcNOA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
