# Kaguya / ArcLINK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/LINK` / `GameRes.Formats.Kaguya.LinkOpener` | `arc` | `4c494e4b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LinkOpener.TryOpen` | `int version = file.View.ReadByte (4) - '0';` |
| `LinkOpener.OpenEntry` | `uint unpacked_size = arc.File.View.ReadUInt32 (entry.Offset);` |
| `LinkOpener.OpenEntry` | `int id = arc.File.View.ReadUInt16 (entry.Offset+5);` |
| `LinkOpener.ReadOldIndex` | `int count = file.View.ReadInt32 (4);` |
| `LinkOpener.ReadOldIndex` | `uint names_size = index.ReadUInt32();` |
| `LinkOpener.ReadOldIndex` | `var name = index.ReadCString();` |
| `LinkOpener.ReadOldIndex` | `entry.Offset = index.ReadUInt32();` |
| `LinkOpener.ReadOldIndex` | `entry.Size   = index.ReadUInt32();` |
| `LinkReader.ReadName` | `int name_length = m_input.ReadUInt8();` |
| `LinkReader.ReadName` | `return m_input.ReadCString (name_length);` |
| `LinkReader.ReadIndex` | `uint size = m_input.ReadUInt32();` |
| `LinkReader.ReadIndex` | `int flags = m_input.ReadUInt16 ();` |
| `LinkReader.ReadIndex` | `if (header.AsciiEqual ("BMR"))` |
| `LinkReader.ReadIndex` | `entry.UnpackedSize = m_input.ReadUInt32();` |
| `Link6Reader.GetDataOffset` | `return 8 + Input.ReadUInt8();` |
| `Link6Reader.ReadName` | `int name_length = Input.ReadUInt16();` |
| `BmrDecoder.BmrDecoder` | `m_step = input.ReadUInt8();` |
| `BmrDecoder.BmrDecoder` | `m_final_size = input.ReadInt32();` |
| `BmrDecoder.BmrDecoder` | `m_key = input.ReadInt32();` |
| `BmrDecoder.BmrDecoder` | `int unpacked_size = input.ReadInt32();` |
| `ParamsDeserializer.Create` | `var header = input.ReadHeader (0x11);` |
| `ParamsDeserializer.Create` | `if (header.AsciiEqual ("[SCR-PARAMS]v0"))` |
| `ParamsDeserializer.ReadKey` | `int key_length = m_input.ReadInt32();` |
| `ParamsDeserializer.ReadKey` | `return m_input.ReadBytes (key_length);` |
| `ParamsDeserializer.ReadString` | `protected virtual string ReadString () {` |
| `ParamsDeserializer.ReadString` | `int length = m_input.ReadUInt8();` |
| `ParamsDeserializer.ReadString` | `return m_input.ReadCString (length);` |
| `ParamsDeserializer.SkipChunk` | `Skip (m_input.ReadUInt8());` |
| `ParamsDeserializer.SkipArray` | `int count = m_input.ReadUInt8();` |
| `ParamsDeserializer.SkipDict` | `int count = m_input.ReadUInt8();` |
| `ParamsDeserializer.ReadHeader` | `protected void ReadHeader (int start) {` |
| `ParamsDeserializer.ReadHeader` | `m_title = ReadString();` |
| `ParamsDeserializer.ReadHeader` | `m_input.ReadCString();` |
| `ParamsDeserializer.ReadHeader` | `m_input.ReadByte();` |
| `ParamsV2Deserializer.GetKey` | `ReadHeader (0x17);` |
| `ParamsV2Deserializer.GetKey` | `int count = m_input.ReadUInt8();` |
| `ParamsV2Deserializer.GetKey` | `m_input.ReadByte();` |
| `ParamsV2Deserializer.GetKey` | `m_input.ReadInt32();` |
| `ParamsV2Deserializer.GetKey` | `return m_input.ReadBytes (240000);` |
| `ParamsV2Deserializer.GetKey` | `count = m_input.ReadUInt8();` |
| `ParamsV4Deserializer.GetKey` | `ReadHeader (0x19);` |
| `ParamsV4Deserializer.GetKey` | `int count = m_input.ReadUInt8();` |
| `ParamsV4Deserializer.GetKey` | `m_input.ReadByte();` |
| `ParamsV4Deserializer.GetKey` | `count = m_input.ReadUInt8();` |
| `ParamsV5Deserializer.GetKey` | `ReadHeader (0x1B);` |
| `ParamsV5Deserializer.GetKey` | `if (0 != m_input.ReadUInt8())` |
| `ParamsV5Deserializer.GetKey` | `Skip (m_input.ReadInt32() * 0xC);` |
| `ParamsV5Deserializer.SkipString` | `int length = m_input.ReadUInt16();` |
| `ParamsV5Deserializer.ReadString` | `protected override string ReadString () {` |
| `ParamsV5Deserializer.ReadString` | `int length = m_input.ReadUInt16();` |
| `ParamsV5Deserializer.SkipTree` | `int count = m_input.ReadInt32();` |
| `ParamsV5Deserializer.SkipTree` | `count = m_input.ReadInt32();` |
| `LinkEncryption.DecryptEntry` | `var header = arc.File.View.ReadBytes (entry.Offset, 4);` |
| `LinkEncryption.DecryptEntry` | `if (header.AsciiEqual (type.Item1))` |
| `LinkEncryption.DecryptImage` | `var header = arc.File.View.ReadBytes (entry.Offset, data_offset);` |
| `LinkEncryption.DecryptAnm` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `LinkEncryption.DecryptAn21` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `LinkEncryption.DecryptAn21` | `int count = data.ToUInt16 (4);` |
| `LinkEncryption.DecryptAn21` | `count = data.ToUInt16 (offset);` |
| `LinkEncryption.DecryptAn21` | `int w = data.ToInt32 (offset);` |
| `LinkEncryption.DecryptAn21` | `int h = data.ToInt32 (offset+4);` |
| `LinkEncryption.DecryptAn21` | `int channels = data.ToInt32 (offset+8);` |
| `LinkEncryption.DecryptPl10` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `LinkEncryption.DecryptPl10` | `int w = data.ToInt32 (offset);` |
| `LinkEncryption.DecryptPl10` | `int h = data.ToInt32 (offset+4);` |
| `LinkEncryption.DecryptPl10` | `int channels = data.ToInt32 (offset+8);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Kaguya.LinkEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public bool IsEncrypted ;

public int  PackType ;
```

### GameRes.Formats.Kaguya.LinkArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly LinkEncryption Encryption ;
```

#### LinkArchive

```csharp
public LinkArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, LinkEncryption enc)
    : base (arc, impl, dir) {
    Encryption = enc;
}
```

### GameRes.Formats.Kaguya.LinkOpener

继承/接口：`ArchiveFormat`。

#### LinkOpener

```csharp
public LinkOpener () {
    Extensions = new string[] { "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadByte (4) - '0';
    if (version < 3 || version > 6)
        return ReadOldIndex (file);

    using (var reader = LinkReader.Create (file, version))
    {
        var dir = reader.ReadIndex();
        if (null == dir)
            return null;

        if (reader.HasEncrypted)
        {
            var enc = reader.GetEncryption();
            if (enc != null)
                return new LinkArchive (file, this, dir, enc);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var lent = entry as LinkEntry;
    if (null == lent || (!lent.IsPacked && !lent.IsEncrypted))
    {
        if (entry.Size > 8)
        {
            uint unpacked_size = arc.File.View.ReadUInt32 (entry.Offset);
            int id = arc.File.View.ReadUInt16 (entry.Offset+5);
            if (id == 0x4D42)
            {
                using (var input = arc.File.CreateStream (entry.Offset+4, entry.Size-4, entry.Name))
                {
                    var data = Lin2Opener.UnpackLzss (input, unpacked_size);
                    return new BinMemoryStream (data, entry.Name);
                }
            }
        }
        return base.OpenEntry (arc, entry);
    }
    if (lent.IsEncrypted)
    {
        var larc = arc as LinkArchive;
        if (null == larc)
            return base.OpenEntry (arc, entry);
        return larc.Encryption.DecryptEntry (larc, lent);
    }
    using (var input = arc.File.CreateStream (entry.Offset, entry.Size))
    {
        if (lent.PackType == 2)
        {
            using (var bmr = new BmrDecoder (input))
            {
                bmr.Unpack();
                return new BinMemoryStream (bmr.Data, entry.Name);
            }
        }
        else if (lent.PackType == 1)
        {
            using (var lz = new LzReader (input, entry.Size, lent.UnpackedSize))
            {
                lz.Unpack();
                return new BinMemoryStream (lz.Data, entry.Name);
            }
        }
        return base.OpenEntry (arc, entry);
    }
}
```

#### ReadOldIndex

```csharp
internal ArcFile ReadOldIndex (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    using (var index = file.CreateStream())
    {
        index.Position = 8;
        uint names_size = index.ReadUInt32();
        for (int i = 0; i < count; ++i)
        {
            var name = index.ReadCString();
            var entry = FormatCatalog.Instance.Create<Entry> (name);
            dir.Add (entry);
        }
        index.Position = 12 + names_size;
        foreach (var entry in dir)
        {
            entry.Offset = index.ReadUInt32();
            entry.Size   = index.ReadUInt32();
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
        }
    }
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.Kaguya.LinkReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

readonly long   m_max_offset ;

bool            m_has_encrypted ;

public IBinaryStream Input { get { return m_input; } }

public bool   HasEncrypted { get { return m_has_encrypted; } }

bool _disposed = false ;
```

#### LinkReader

```csharp
protected LinkReader (ArcView file) {
    m_input = file.CreateStream();
    m_max_offset = file.MaxOffset;
    m_has_encrypted = false;
}
```

#### Create

```csharp
public static LinkReader Create (ArcView file, int version) {
    if (version < 4)
        return new LinkReader (file);
    else if (version < 6)
        return new Link4Reader (file);
    else
        return new Link6Reader (file);
}
```

#### GetDataOffset

```csharp
protected virtual long GetDataOffset () {
    return 8;
}
```

#### ReadName

```csharp
protected virtual string ReadName () {
    int name_length = m_input.ReadUInt8();
    Skip (2);
    return m_input.ReadCString (name_length);
}
```

#### ReadIndex

```csharp
public List<Entry> ReadIndex () {
    m_input.Position = GetDataOffset();

    var header = new byte[4];
    var dir = new List<Entry>();
    while (m_input.Position + 4 < m_max_offset)
    {
        long base_offset = m_input.Position;
        uint size = m_input.ReadUInt32();
        if (0 == size)
            break;
        if (size < 0x10)
            return null;
        int flags = m_input.ReadUInt16 ();
        Skip (7);
        var name = ReadName();
        if (string.IsNullOrEmpty (name))
            return null;
        var entry = FormatCatalog.Instance.Create<LinkEntry> (name);
        entry.Offset   = m_input.Position;
        entry.Size     = size - (uint)(entry.Offset - base_offset);
        entry.PackType = flags & 3;
        if (entry.PackType == 2)
        {
            m_input.Read (header, 0, 4);
            if (header.AsciiEqual ("BMR"))
            {
                entry.IsPacked = true;
                entry.UnpackedSize = m_input.ReadUInt32();
            }
        }
        else if (entry.PackType == 1)
        {
            entry.IsPacked = true;
            entry.Offset += 4;
            entry.Size -= 4;
            entry.UnpackedSize = m_input.ReadUInt32();
        }
        entry.IsEncrypted = (flags & 4) != 0;
        m_has_encrypted = m_has_encrypted || entry.IsEncrypted;
        dir.Add (entry);
        m_input.Position = entry.Offset + entry.Size;
    }
    return dir;
}
```

#### GetEncryption

```csharp
public virtual LinkEncryption GetEncryption () {
    var params_dat = VFS.ChangeFileName (m_input.Name, "params.dat");
    if (!VFS.FileExists (params_dat))
        return null;

    using (var input = VFS.OpenBinaryStream (params_dat))
    {
        var param = ParamsDeserializer.Create (input);
        return param.GetEncryption();
    }
}
```

#### Skip

```csharp
protected void Skip (int amount) {
    m_input.Seek (amount, SeekOrigin.Current);
}
```

### GameRes.Formats.Kaguya.Link4Reader

继承/接口：`LinkReader`。

#### GetDataOffset

```csharp
protected override long GetDataOffset () {
    return 0xA;
}
```

### GameRes.Formats.Kaguya.Link6Reader

继承/接口：`LinkReader`。

#### 状态与常量

```csharp
byte[] name_buffer = new byte[0x100] ;
```

#### GetDataOffset

```csharp
protected override long GetDataOffset () {
    Input.Position = 7;
    return 8 + Input.ReadUInt8();
}
```

#### ReadName

```csharp
protected override string ReadName () {
    int name_length = Input.ReadUInt16();
    if (name_length > 0x400)
        throw new InvalidFormatException();
    if (name_length > name_buffer.Length)
        name_buffer = new byte[name_length];
    Input.Read (name_buffer, 0, name_length);
    return Encoding.Unicode.GetString (name_buffer, 0, name_length);
}
```

### GameRes.Formats.Kaguya.BmrDecoder

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
byte[]          m_output ;

MsbBitStream    m_input ;

int             m_final_size ;

int             m_step ;

int             m_key ;

public byte[] Data { get { return m_output; } }

ushort      m_token ;

ushort[,]   m_tree = new ushort[2,256] ;

bool _disposed = false ;
```

#### BmrDecoder

```csharp
public BmrDecoder (IBinaryStream input) {
    input.Position = 3;
    m_step = input.ReadUInt8();
    m_final_size = input.ReadInt32();
    m_key = input.ReadInt32();
    int unpacked_size = input.ReadInt32();
    m_output = new byte[unpacked_size];
    m_input = new MsbBitStream (input.AsStream, true);
}
```

#### Unpack

```csharp
public void Unpack () {
    m_input.Input.Position = 0x14;
    UnpackHuffman();
    UndoMoveToFront();
    m_output = Decode (m_output, m_key);
    if (m_step != 0)
        m_output = DecompressRLE (m_output);
}
```

#### DecompressRLE

```csharp
byte[] DecompressRLE (byte[] input) {
    var result = new byte[m_final_size];
    int src = 0;
    for (int i = 0; i < m_step; ++i)
    {
        byte v1 = input[src++];
        result[i] = v1;
        int dst = i + m_step;
        while (dst < result.Length)
        {
            byte v2 = input[src++];
            result[dst] = v2;
            dst += m_step;
            if (v2 == v1)
            {
                int count = input[src++];
                if (0 != (count & 0x80))
                    count = input[src++] + ((count & 0x7F) << 8) + 128;
                while (count --> 0 && dst < result.Length)
                {
                    result[dst] = v2;
                    dst += m_step;
                }
                if (dst < result.Length)
                {
                    v2 = input[src++];
                    result[dst] = v2;
                    dst += m_step;
                }
            }
            v1 = v2;
        }
    }
    return result;
}
```

#### UndoMoveToFront

```csharp
void UndoMoveToFront () {
    var dict = new byte[256];
    for (int i = 0; i < 256; ++i)
        dict[i] = (byte)i;
    for (int i = 0; i < m_output.Length; ++i)
    {
        byte v = m_output[i];
        m_output[i] = dict[v];
        for (int j = v; j > 0; --j)
        {
            dict[j] = dict[j-1];
        }
        dict[0] = m_output[i];
    }
}
```

#### Decode

```csharp
byte[] Decode (byte[] input, int key) {
    var freq_table = new int[256];
    for (int i = 0; i < input.Length; ++i)
    {
        ++freq_table[input[i]];
    }
    for (int i = 1; i < 256; ++i)
    {
        freq_table[i] += freq_table[i-1];
    }
    var distrib_table = new int[input.Length];
    for (int i = input.Length-1; i >= 0; --i)
    {
        int v = input[i];
        int freq = --freq_table[v];
        distrib_table[freq] = i;
    }
    int pos = key;
    var copy_out = new byte[input.Length];
    for (int i = 0; i < copy_out.Length; ++i)
    {
        pos = distrib_table[pos];
        copy_out[i] = input[pos];
    }
    return copy_out;
}
```

#### UnpackHuffman

```csharp
void UnpackHuffman () {
    m_token = 256;
    ushort root = CreateHuffmanTree();
    int dst = 0;
    while (dst < m_output.Length)
    {
        ushort symbol = root;
        while (symbol >= 0x100)
        {
            int bit = m_input.GetNextBit();
            if (-1 == bit)
                throw new EndOfStreamException();
            symbol = m_tree[bit,symbol-256];
        }
        m_output[dst++] = (byte)symbol;
    }
}
```

#### CreateHuffmanTree

```csharp
ushort CreateHuffmanTree () {
    if (0 != m_input.GetNextBit())
    {
        ushort v = m_token++;
        m_tree[0,v-256] = CreateHuffmanTree();
        m_tree[1,v-256] = CreateHuffmanTree();
        return v;
    }
    else
    {
        return (ushort)m_input.GetBits (8);
    }
}
```

### GameRes.Formats.Kaguya.ParamsDeserializer

#### 状态与常量

```csharp
protected IBinaryStream     m_input ;

protected string            m_title ;

protected Version           m_version ;
```

#### ParamsDeserializer

```csharp
protected ParamsDeserializer (IBinaryStream input, Version version) {
    m_input = input;
    m_version = version;
}
```

#### Create

```csharp
public static ParamsDeserializer Create (IBinaryStream input) {
    var header = input.ReadHeader (0x11);
    if (header.AsciiEqual ("[SCR-PARAMS]v0"))
    {
        Version version;
        if ('.' == header[15])
            version = Version.Parse (header.GetCString (13, 4));
        else
            version = new Version (header[14] - '0', 0);
        if (2 == version.Major)
            return new ParamsV2Deserializer (input, version);
        else if (version.Major < 5)
            return new ParamsV4Deserializer (input, version);
        else if (5 == version.Major && (version.Minor >= 4 && version.Minor <= 8))
            return new ParamsV5Deserializer (input, version);
    }
    throw new UnknownEncryptionScheme();
}
```

#### GetEncryption

```csharp
public virtual LinkEncryption GetEncryption () {
    return new LinkEncryption (GetKey());
}
```

#### GetKey

```csharp
public abstract byte[] GetKey () ;
```

#### ReadKey

```csharp
protected byte[] ReadKey () {
    int key_length = m_input.ReadInt32();
    return m_input.ReadBytes (key_length);
}
```

#### ReadString

```csharp
protected virtual string ReadString () {
    int length = m_input.ReadUInt8();
    return m_input.ReadCString (length);
}
```

#### SkipString

```csharp
protected virtual void SkipString () {
    SkipChunk();
}
```

#### Skip

```csharp
protected void Skip (int amount) {
    m_input.Seek (amount, SeekOrigin.Current);
}
```

#### SkipChunk

```csharp
protected void SkipChunk () {
    Skip (m_input.ReadUInt8());
}
```

#### SkipArray

```csharp
protected void SkipArray () {
    int count = m_input.ReadUInt8();
    for (int i = 0; i < count; ++i)
        SkipChunk();
}
```

#### SkipDict

```csharp
protected void SkipDict () {
    int count = m_input.ReadUInt8();
    for (int i = 0; i < count; ++i)
    {
        SkipString();
        SkipString();
    }
}
```

#### ReadHeader

```csharp
protected void ReadHeader (int start) {
    m_input.Position = start;
    SkipChunk();
    m_title = ReadString();
    if (m_version.Major < 2)
        m_input.ReadCString();

    SkipString();
    SkipString();
    m_input.ReadByte();
    SkipString();
    SkipString();
    SkipDict();
    m_input.ReadByte();
}
```

### GameRes.Formats.Kaguya.ParamsV2Deserializer

继承/接口：`ParamsDeserializer`。

#### GetEncryption

```csharp
public override LinkEncryption GetEncryption () {
    var key = GetKey();
    return new LinkEncryption (key, m_title != "幼なじみと甘～くエッチに過ごす方法");
}
```

#### GetKey

```csharp
public override byte[] GetKey () {
    ReadHeader (0x17);

    if ("幼なじみと甘～くエッチに過ごす方法" == m_title || "艶女医" == m_title)
    {
        int count = m_input.ReadUInt8();
        for (int i = 0; i < count; ++i)
        {
            m_input.ReadByte();
            SkipChunk();
            SkipArray();
            SkipChunk();
        }
        SkipArray();
        SkipArray();
        if ("幼なじみと甘～くエッチに過ごす方法" == m_title)
        {
            m_input.ReadInt32();
            return m_input.ReadBytes (240000);
        }
        else
        {
            return ReadKey();
        }
    }
    else
    {
        int count = m_input.ReadUInt8();
        for (int i = 0; i < count; ++i)
        {
            m_input.ReadByte();
            SkipChunk();
            SkipArray();
            SkipArray();
        }
        SkipDict();
        count = m_input.ReadUInt8();
        for (int i = 0; i < count; ++i)
        {
            SkipChunk();
            SkipArray();
            SkipArray();
        }
        return ReadKey();
    }
}
```

### GameRes.Formats.Kaguya.ParamsV4Deserializer

继承/接口：`ParamsDeserializer`。

#### GetKey

```csharp
public override byte[] GetKey () {
    ReadHeader (0x19);

    Skip (m_version.Major < 5 ? 12 : 11);
    int count = m_input.ReadUInt8();
    for (int i = 0; i < count; ++i)
    {
        m_input.ReadByte();
        SkipChunk();
        SkipArray();
        SkipArray();
    }
    SkipDict();
    count = m_input.ReadUInt8();
    for (int i = 0; i < count; ++i)
    {
        SkipChunk();
        SkipArray();
        SkipArray();
    }
    return ReadKey();
}
```

### GameRes.Formats.Kaguya.ParamsV5Deserializer

继承/接口：`ParamsDeserializer`。

#### 状态与常量

```csharp
byte[] name_buffer = new byte[0x100] ;
```

#### GetKey

```csharp
public override byte[] GetKey () {
    ReadHeader (0x1B);

    Skip (m_version.Minor <= 4 ? 15 : 16);
    for (int i = 0; i < 3; ++i)
    {
        if (0 != m_input.ReadUInt8())
            SkipTree();
    }
    Skip (m_input.ReadInt32() * 0xC);
    return ReadKey();
}
```

#### SkipString

```csharp
protected override void SkipString () {
    int length = m_input.ReadUInt16();
    Skip (length);
}
```

#### ReadString

```csharp
protected override string ReadString () {
    int length = m_input.ReadUInt16();
    if (length > name_buffer.Length)
        name_buffer = new byte[length];
    m_input.Read (name_buffer, 0, length);
    return Encoding.Unicode.GetString (name_buffer, 0, length);
}
```

#### SkipTree

```csharp
protected void SkipTree () {
    SkipString();
    int count = m_input.ReadInt32();
    while (count --> 0)
    {
        SkipString();
        SkipString();
    }
    count = m_input.ReadInt32();
    while (count --> 0)
        SkipTree();
}
```

### GameRes.Formats.Kaguya.LinkEncryption

#### 状态与常量

```csharp
byte[]   m_key ;

Tuple<string, Decryptor>[] m_type_table ;

static readonly ResourceInstance<AnmOpener>  An00 = new ResourceInstance<AnmOpener> ("ANM/KAGUYA") ;

static readonly ResourceInstance<An10Opener> An10 = new ResourceInstance<An10Opener> ("AN10/KAGUYA") ;

static readonly ResourceInstance<An20Opener> An20 = new ResourceInstance<An20Opener> ("AN20/KAGUYA") ;

static readonly ResourceInstance<Pl00Opener> Pl00 = new ResourceInstance<Pl00Opener> ("PLT/KAGUYA") ;
```

#### Decryptor

```csharp
delegate Stream Decryptor (LinkArchive arc, LinkEntry entry) ;
```

#### LinkEncryption

```csharp
public LinkEncryption (byte[] key, bool anm_encrypted = true) {
    if (null == key || 0 == key.Length)
        throw new ArgumentException ("Invalid encryption key");
    m_key = key;
    var table = new List<Tuple<string, Decryptor>>
    {
        new Tuple<string, Decryptor> ("BM",     (a, e) => DecryptImage (a, e, 0x36)),
        new Tuple<string, Decryptor> ("AP-2",   (a, e) => DecryptImage (a, e, 0x18)),
        new Tuple<string, Decryptor> ("AP-3",   (a, e) => DecryptImage (a, e, 0x18)),
        new Tuple<string, Decryptor> ("AP",     (a, e) => DecryptImage (a, e, 0xC)),
    };
    if (anm_encrypted)
    {
        table.Add (new Tuple<string, Decryptor> ("AN00", (a, e) => DecryptAnm (a, e, An00.Value)));
        table.Add (new Tuple<string, Decryptor> ("AN10", (a, e) => DecryptAnm (a, e, An10.Value)));
        table.Add (new Tuple<string, Decryptor> ("AN20", (a, e) => DecryptAnm (a, e, An20.Value)));
        table.Add (new Tuple<string, Decryptor> ("AN21", (a, e) => DecryptAn21 (a, e)));
        table.Add (new Tuple<string, Decryptor> ("PL00", (a, e) => DecryptAnm (a, e, Pl00.Value)));
        table.Add (new Tuple<string, Decryptor> ("PL10", (a, e) => DecryptPl10 (a, e)));
    }
    m_type_table = table.ToArray();
}
```

#### DecryptEntry

```csharp
public Stream DecryptEntry (LinkArchive arc, LinkEntry entry) {
    var header = arc.File.View.ReadBytes (entry.Offset, 4);
    foreach (var type in m_type_table)
    {
        if (header.AsciiEqual (type.Item1))
            return type.Item2 (arc, entry);
    }
    return arc.File.CreateStream (entry.Offset, entry.Size);
}
```

#### DecryptImage

```csharp
Stream DecryptImage (LinkArchive arc, LinkEntry entry, uint data_offset) {
    var header = arc.File.View.ReadBytes (entry.Offset, data_offset);
    Stream body = arc.File.CreateStream (entry.Offset+data_offset, entry.Size-data_offset);
    body = new ByteStringEncryptedStream (body, m_key);
    return new PrefixStream (header, body);
}
```

#### DecryptAnm

```csharp
Stream DecryptAnm (LinkArchive arc, LinkEntry entry, IAnmReader reader) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    var input = new BinMemoryStream (data, entry.Name);
    var dir = reader.GetFramesList (input);
    if (dir != null)
    {
        foreach (AnmEntry frame in dir)
        {
            DecryptData (data, (int)frame.ImageDataOffset, (int)frame.ImageDataSize);
        }
    }
    input.Position = 0;
    return input;
}
```

#### DecryptAn21

```csharp
Stream DecryptAn21 (LinkArchive arc, LinkEntry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    int count = data.ToUInt16 (4);
    int offset = 8;
    for (int i = 0; i < count; ++i)
    {
        switch (data[offset++])
        {
        case 0: break;
        case 1: offset += 8; break;
        case 2:
        case 3:
        case 4:
        case 5: offset += 4; break;
        default: return new BinMemoryStream (data, entry.Name);
        }
    }
    count = data.ToUInt16 (offset);
    offset += 2 + count * 8 + 0x21;
    int w = data.ToInt32 (offset);
    int h = data.ToInt32 (offset+4);
    int channels = data.ToInt32 (offset+8);
    offset += 12;
    DecryptData (data, offset, channels * w * h);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptPl10

```csharp
Stream DecryptPl10 (LinkArchive arc, LinkEntry entry) {
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    int offset = 30;
    int w = data.ToInt32 (offset);
    int h = data.ToInt32 (offset+4);
    int channels = data.ToInt32 (offset+8);
    offset += 12;
    DecryptData (data, offset, channels * w * h);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, int index, int length) {
    while (length > 0)
    {
        int count = Math.Min (length, m_key.Length);
        for (int i = 0; i < count; ++i)
        {
            data[index++] ^= m_key[i];
        }
        length -= count;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。
- [ArcFormats/Kaguya/ArcANM.cs](ArcANM.md)：本页引用的随包算法资料。
- [ArcFormats/Kaguya/ArcKaguya.cs](ArcKaguya.md)：本页引用的随包算法资料。
- [ArcFormats/Kaguya/ArcLIN2.cs](ArcLIN2.md)：本页引用的随包算法资料。
- [ArcFormats/Kaguya/ArcPLT.cs](ArcPLT.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Kaguya/ArcLINK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
