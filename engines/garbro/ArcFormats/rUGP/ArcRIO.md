# rUGP / ArcRIO：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `RIO` / `GameRes.Formats.Rugp.RioOpener` | `rio` | `cd326e59` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `RioReader.Create` | `if (CRioArchive.RioSignature == file.View.ReadUInt32 (0))` |
| `RioReader.RioReader` | `uint signature = file.View.ReadUInt32 (toc_offset);` |
| `RioReader.RioReader` | `signature = file.View.ReadUInt32 (toc_offset);` |
| `CRioArchive.ReadObject` | `int f1 = ReadByte() & 3;` |
| `CRioArchive.ReadObject` | `int f2 = ReadByte();` |
| `CRioArchive.ReadObject` | `int f3 = ReadByte();` |
| `CRioArchive.ReadObject` | `case 2: f4 = (f3 & 0xFE) << 1 \| (ReadByte() & 0xC0) << 1; break;` |
| `CRioArchive.ReadObject` | `case 3: f4 = (f3 & 0xFE) << 1 \| (ReadByte() & 0xFE) << 6; break;` |
| `CRioArchive.ReadObject` | `int flags = ReadUInt16();` |
| `CRioArchive.ReadObject` | `int schema = ReadUInt16();` |
| `CRioArchive.LoadRioTypeCore` | `signature = m_input.ReadUInt32();` |
| `CRioArchive.LoadRioTypeCore` | `int version = ReadUInt16();` |
| `CRioArchive.LoadRioTypeCore` | `m_field_4C \|= ReadUInt16() << 16;` |
| `CRioArchive.DeserializeClassList` | `m_field_50 = ReadString();` |
| `CRioArchive.DeserializeNode` | `int flags = ReadUInt16();` |
| `CRioArchive.DeserializeNode` | `ReadByte();` |
| `CRioArchive.DeserializeNode` | `ReadUInt16();` |
| `CRioArchive.DeserializeNode` | `ReadInt32();` |
| `CRioArchive.DeserializeNode` | `int id1 = ReadInt32();` |
| `CRioArchive.DeserializeNode` | `int id2 = ReadInt32();` |
| `CRioArchive.DeserializeNode` | `int id = ReadInt32();` |
| `CRioArchive.ReadCType` | `int c = ReadUInt16();` |
| `CRioArchive.ReadMessage` | `int id = ReadUInt16();` |
| `CRioArchive.ReadMessage` | `int cLen = ReadUInt16();` |
| `CRioArchive.ReadBasicType` | `ReadUInt16();` |
| `CRioArchive.ReadBasicType` | `int cLen = ReadUInt16();` |
| `CRioArchive.ReadMsgClass` | `int wTag = ReadUInt16();` |
| `CRioArchive.ReadMsgClass` | `obTag = ReadInt32();` |
| `CRioArchive.ReadRioReference` | `int flags = ReadUInt16();` |
| `CRioArchive.ReadRioReference` | `id1 = ReadInt32();` |
| `CRioArchive.ReadRioReference` | `id2 = ReadInt32();` |
| `CRioArchive.ReadRioReference` | `name = ReadString();` |
| `CRioArchive.ReadRioReference` | `ReadInt32();` |
| `CRioArchive.ReadRioReference` | `ReadByte();` |
| `CRioArchive.ReadRioReference` | `ReadUInt16();` |
| `CRioArchive.ReadClass` | `int wTag = ReadUInt16();` |
| `CRioArchive.ReadClass` | `obTag = ReadInt32();` |
| `CRioArchive.LoadRuntimeClass` | `schema = ReadUInt16();` |
| `CRioArchive.LoadRuntimeClass` | `int nLen = ReadUInt16();` |
| `CRioArchive.LoadScrambledClass` | `schema = ReadUInt16();` |
| `CRioArchive.LoadScrambledClass` | `int length = ReadByte();` |
| `CRioArchive.LoadScrambledClass` | `length = ReadUInt16();` |
| `CRioArchive.ReadInt32` | `public int ReadInt32 () {` |
| `CRioArchive.ReadInt32` | `return m_input.ReadInt32();` |
| `CRioArchive.ReadInt64` | `public long ReadInt64 () {` |
| `CRioArchive.ReadInt64` | `return m_input.ReadInt64();` |
| `CRioArchive.ReadUInt16` | `public ushort ReadUInt16 () {` |
| `CRioArchive.ReadUInt16` | `return m_input.ReadUInt16();` |
| `CRioArchive.ReadByte` | `public byte ReadByte () {` |
| `CRioArchive.ReadByte` | `return m_input.ReadUInt8();` |
| `CRioArchive.ReadBytes` | `public byte[] ReadBytes (int count) {` |
| `CRioArchive.ReadBytes` | `return m_input.ReadBytes (count);` |
| `CRioArchive.ReadBool` | `return m_input.ReadUInt8() != 0;` |
| `CRioArchive.ReadString` | `public string ReadString () {` |
| `CRioArchive.ReadString` | `var buffer = m_input.ReadBytes (nLength);` |
| `CRioArchive.ReadCount` | `int count = ReadUInt16();` |
| `CRioArchive.ReadCount` | `return ReadInt32();` |
| `CRioArchive.ReadShortCount` | `int count = ReadByte();` |
| `CRioArchive.ReadShortCount` | `return ReadUInt16();` |
| `CRioArchive.ReadStringLength` | `int length = ReadByte();` |
| `CRioArchive.ReadStringLength` | `length = ReadUInt16();` |
| `CRioArchive.ReadStringLength` | `return ReadInt32();` |
| `CRioArchive.ReadEncrypted` | `uint size1 = m_input.ReadUInt32() ^ 0xC92E568B;` |
| `CRioArchive.ReadEncrypted` | `uint size2 = m_input.ReadUInt32() ^ 0xC92E568F;` |
| `CRioArchive.ReadEncrypted` | `ushort chunk_sum = m_input.ReadUInt16();` |
| `CStringArray.Deserialize` | `m_data[i] = arc.ReadString();` |
| `CInstallSource.Deserialize` | `Version = arc.ReadUInt16();` |
| `CInstallSource.Deserialize` | `field_14 = arc.ReadInt32();` |
| `CInstallSource.Deserialize` | `field_18 = arc.ReadInt32();` |
| `CInstallSource.Deserialize` | `arc.ReadByte();` |
| `CInstallSource.Deserialize` | `arc.ReadString();` |
| `CInstallSource.Deserialize` | `arc.ReadInt64();` |
| `CInstallSource.Deserialize` | `arc.ReadInt32();` |
| `CInstallSource.Deserialize` | `RioName = arc.ReadString();` |
| `CInstallSource.Deserialize` | `RioOffset = arc.ReadInt64();` |
| `CInstallSource.Deserialize` | `RioSize = arc.ReadInt64();` |
| `CInstallSource.Deserialize` | `arc.ReadBytes (count*4);` |
| `CObjectArcMan.Deserialize` | `Version = arc.ReadInt32();` |
| `CObjectArcMan.Deserialize` | `field_14 = arc.ReadInt32();` |
| `CObjectArcMan.Deserialize` | `arc.ReadByte();` |
| `CObjectArcMan.Deserialize` | `field_1C = arc.ReadInt32();` |
| `CObjectArcMan.Deserialize` | `field_20 = arc.ReadInt32();` |
| `CObjectArcMan.Deserialize` | `arc.ReadInt32();` |
| `CObjectArcMan.Deserialize` | `TocOffset = arc.ReadInt32();` |
| `CObjectArcMan.Deserialize` | `TocSize   = arc.ReadInt32();` |
| `CObjectArcMan.Deserialize` | `field_38 = arc.ReadInt32();` |
| `CObjectArcMan.Deserialize` | `Title = arc.ReadString();` |
| `CObjectArcMan.Deserialize` | `arc.ReadString();` |
| `CObjectArcMan.Deserialize` | `RioFileName = arc.ReadString();` |
| `CObjectArcMan.Deserialize` | `field_98 = arc.ReadInt32();` |
| `CrelicUnitedGameProject.ReadRelic` | `Version = arc.ReadInt32();` |
| `CUnknown1.Deserialize` | `Version = arc.ReadInt32();` |
| `CUnknown1.Deserialize` | `field_04 = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_08 = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_0C = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_14 = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_1C = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_18 = arc.ReadInt32();` |
| `CUnknown1.Deserialize` | `field_28 = arc.ReadBytes (16);` |
| `CUnknown1.Deserialize` | `field_38 = arc.ReadInt32();` |
| `CUnknown1.Deserialize` | `field_3C = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_40 = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_44 = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_10 = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_20 = arc.ReadInt32();` |
| `CUnknown1.Deserialize` | `field_24 = arc.ReadInt32();` |
| `CUnknown1.Deserialize` | `if (field_28.ToUInt16 (0) < 0x7D3)` |
| `CUnknown1.Deserialize` | `field_48 = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_4C = arc.ReadString();` |
| `CUnknown1.Deserialize` | `field_50 = arc.ReadString();` |
| `CStdb.Deserialize` | `field_0C = arc.ReadString();` |
| `CBoxOcean.Deserialize` | `field_118.Add (arc.ReadString());` |
| `CBoxOcean.ReadCui` | `while (arc.ReadByte() != 0)` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Rugp.RioOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Dictionary<string, string> SupportedClasses = new Dictionary<string, string> {
    { "CRip007",                "image" },
    { "CRip",                   "image" },
    { "CS5i",                   "image" },
    { "CIcon",                  "image" },
    { "CRioPng",                "image" },
    { "CRsa",                   "script" },
    { "CVmFunc",                "script" },
    { "CSinpleText",            "script" },
    { "CrUAVMScript",           "script" },
    { "CrUAVMTextScript",       "script" },
    { "CrUAVMTextScriptHeader", "script" },
    { "CWaveAudio",             "audio" },
    { "CrelicHicompAudio",      "audio" },
    { "COggStream",             "audio" },
    { "CWindowsMediaVideo",     "video" },
}
```

#### RioOpener

```csharp
public RioOpener () {
    Signatures = new uint[] { CRioArchive.RioSignature, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    using (var reader = RioReader.Create (file))
    {
        if (null == reader)
            return null;
        reader.DeserializeRelic();
        var nodes = reader.Arc.LoadArray.OfType<COceanNode>();
        var types = nodes.Select (n => n.ClassName).Distinct();
        var dir = from node in nodes
                  where SupportedClasses.ContainsKey (node.ClassName)
                  select new Entry {
                    Name    = node.GetPathName(),
                    Type    = SupportedClasses[node.ClassName],
                    Offset  = node.Offset,
                    Size    = node.Size
                  };
        if (!dir.Any())
        {
            var box_ref = nodes.FirstOrDefault (n => n.ClassName == "CBoxOcean");
            if (null == box_ref)
                return null;
            var box = reader.ReadObject (box_ref);
            nodes = reader.Arc.LoadArray.OfType<COceanNode>();
        }
        return new ArcFile (file, this, dir.ToList());
    }
}
```

### GameRes.Formats.Rugp.RioReader

继承/接口：`IDisposable`。

#### 状态与常量

```csharp
IBinaryStream   m_input ;

IBinaryStream   m_toc ;

CRioArchive     m_arc ;

bool            m_read_toc ;

CrelicUnitedGameProject     m_relic ;

const uint IciKey = 0xB29D5A0C ;

public CRioArchive Arc { get { return m_arc; } }

bool _disposed = false ;
```

#### DeserializeRelic

```csharp
public CrelicUnitedGameProject DeserializeRelic () {
    if (!m_read_toc)
    {
        m_read_toc = true;
        m_relic = m_arc.DeserializeRoot() as CrelicUnitedGameProject;
        if (m_toc != m_input)
        {
            m_toc.Dispose();
            m_toc = m_input;
            m_arc.SetSource (m_input);
        }
    }
    return m_relic;
}
```

#### Create

```csharp
static public RioReader Create (ArcView file) {
    if (CRioArchive.RioSignature == file.View.ReadUInt32 (0))
        return new RioReader (file);

    if (file.Name.HasExtension (".ici"))
        return null;
    var ici_name = file.Name + ".ici";
    if (!VFS.FileExists (ici_name))
    {
        ici_name = Path.ChangeExtension (file.Name, ".ici");
        if (!VFS.FileExists (ici_name))
            return null;
    }
    byte[] ici_data;
    using (var ici = VFS.OpenBinaryStream (ici_name))
        ici_data = ReadIci (ici, IciKey);

    CObjectArcMan arc_man;
    using (var ici = new BinMemoryStream (ici_data))
    {
        var rio = new CRioArchive (ici);
        arc_man = rio.DeserializeRoot() as CObjectArcMan;
        if (null == arc_man)
            return null;
    }
    var arc_object = arc_man.ArcList.FirstOrDefault();
    if (null == arc_object || !VFS.IsPathEqualsToFileName (file.Name, arc_object.RioName))
        return null;
    return new RioReader (arc_man, file);
}
```

#### RioReader

```csharp
private RioReader (ArcView file) {
    m_input = file.CreateStream();
    m_toc = m_input;
    m_arc = new CRioArchive (m_input);
}
```

#### RioReader

```csharp
private RioReader (CObjectArcMan arc_man, ArcView file) {
    long toc_offset = arc_man.TocOffset;
    uint signature = file.View.ReadUInt32 (toc_offset);
    int shift = 0;
    if (signature != CRioArchive.EncryptedSignature)
    {
        toc_offset *= 2;
        signature = file.View.ReadUInt32 (toc_offset);
        if (signature != CRioArchive.EncryptedSignature)
            throw new InvalidFormatException ("CPmArchive signature not found");
        shift = 1;
    }
    m_input = file.CreateStream();
    m_toc = file.CreateStream (toc_offset, (uint)arc_man.TocSize);
    m_arc = new CRioArchive (m_toc, shift, true);
}
```

#### ReadObject

```csharp
public CObject ReadObject (COceanNode node) {
    return m_arc.ReadObject (node);
}
```

#### ReadIci

```csharp
static byte[] ReadIci (IBinaryStream ici, uint key) {
    var rio = new CRioArchive (ici);
    var ici_data = rio.ReadEncrypted (key);
    return DecryptIci (ici_data);
}
```

#### DecryptIci

```csharp
static byte[] DecryptIci (byte[] input) {
    var output = new byte[input.Length];
    int src = 0;
    int dst = 0;
    int tail_size;
    int chunk_count = Math.DivRem (input.Length, 6, out tail_size);
    for (int n = chunk_count; n > 0; --n)
    {
        output[dst++] = input[src];
        output[dst++] = input[src + chunk_count];
        output[dst++] = input[src + chunk_count * 2];
        output[dst++] = input[src + chunk_count * 3];
        output[dst++] = input[src + chunk_count * 4];
        output[dst++] = input[src + chunk_count * 5];
        ++src;
    }
    if (tail_size > 0)
        Buffer.BlockCopy (input, input.Length - tail_size, output, dst, tail_size);

    byte acc = 0;
    for (int i = 0; i < output.Length; ++i)
    {
        output[i] -= acc;
        acc += output[i];
        output[i] ^= 0xA5;
    }

    src = 0;
    dst = 0;
    chunk_count = Math.DivRem (input.Length, 5, out tail_size);
    for (int n = chunk_count; n > 0; --n)
    {
        input[dst++] = output[src];
        input[dst++] = output[src + chunk_count];
        input[dst++] = output[src + chunk_count * 2];
        input[dst++] = output[src + chunk_count * 3];
        input[dst++] = output[src + chunk_count * 4];
        ++src;
    }
    if (tail_size > 0)
        Buffer.BlockCopy (output, output.Length - tail_size, input, dst, tail_size);

    acc = 0;
    for (int i = input.Length-1; i >= 0; --i)
    {
        input[i] -= acc;
        acc += input[i];
    }

    src = 0;
    dst = 0;
    chunk_count = Math.DivRem (input.Length, 3, out tail_size);
    for (int n = chunk_count; n > 0; --n)
    {
        output[dst++] = (byte)(input[src] ^ 0x18);
        output[dst++] = (byte)(input[src + chunk_count] ^ 0x3F);
        output[dst++] = (byte)(input[src + chunk_count * 2] ^ 0xE2);
        ++src;
    }
    if (tail_size > 0)
        Buffer.BlockCopy (input, input.Length - tail_size, output, dst, tail_size);

    return output;
}
```

### GameRes.Formats.Rugp.CRioArchive

#### 状态与常量

```csharp
IBinaryStream   m_input ;

int             m_field_4C ;

string          m_field_50 ;

int             m_field_54 ;

bool            m_field_60 ;

int             m_shift ;

int             m_objectSchema = -1 ;

Dictionary<int, COceanNode> m_OceanMap = new Dictionary<int, COceanNode>() ;

ArrayList                   m_LoadArray = new ArrayList() ;

public IBinaryStream Input { get { return m_input; } }

public ArrayList LoadArray { get { return m_LoadArray; } }

public  bool   IsEncrypted { get { return 0 != (m_field_4C & 4); } }

private bool    m_field_5C { get { return IsEncrypted; } }

public int          Schema { get; private set; }

public const uint EncryptedSignature    = 0x1EDB927C ;

public const uint ObjectSignature       = 0x29F6CBA4 ;

public const uint RioSignature          = 0x596E32CD ;

public const uint IciSignature          = 0x673CE92A ;

static readonly ISet<uint> CoreSignatures = new HashSet<uint> {
    IciSignature, EncryptedSignature, RioSignature, ObjectSignature
}

int m_depth = 0 ;

const int MaxRecursionDepth = 40 ;

const int wClassTag     = 0x8000 ;

const int dwBigClassTag = (int)-0x80000000 ;

byte[] m_name_buf = new byte[0x100] ;

static readonly char[] CharMap1 = {
'e', 'a', 'i', 't', 'r', 'o', 's', 'd', 'u', 'c', 'm', 'n', 'S', 'g', 'l', 'R' }

static readonly char[] CharMap2 = {
'\x1', 'C', 'O', 'F', 'L', 'f', 'B', 'M', 'x', 'p', 'h', 'y', 'A', 'V', 'b', 'I' }

static readonly char[] CharMap3 = {
'E', 'H', 'T', 'D', 'P', 'W', 'X', 'k', 'q', 'v', 'N', 'j', 'w', 'G', 'z', '0',
'2', 'U', '_', 'K', '1', '5', 'J', 'Q', 'Z', '4', '6', '7', '8', '3', '9', '\x0' }

static readonly Dictionary<string, string> s_basicTypeList = new Dictionary<string, string> {
    { "バイト",     "byte"   },
    { "短正整数",   "short"  },
    { "短整数",     "ushort" },
    { "正整数",     "int"    },
    { "整数",       "uint"   },
    { "色",         "Color"  },
}

static readonly Dictionary<string, IObjectFactory> s_classTable = new Dictionary<string, IObjectFactory> {
    { "CObjectArcMan", new CObjectFactory<CObjectArcMan>() },
    { "CrelicUnitedGameProject", new CObjectFactory<CrelicUnitedGameProject>() },
    { "CStdb", new CObjectFactory<CStdb>() },
    { "CObjectOcean", new CObjectFactory<CObjectOcean>() },
    { "CBoxOcean", new CObjectFactory<CBoxOcean>() },
    { "CRio", new CObjectFactory<CRio>() },
}
```

#### CRioArchive

```csharp
public CRioArchive (IBinaryStream input) {
    m_input = input;
}
```

#### CRioArchive

```csharp
public CRioArchive (IBinaryStream input, int shift, bool encrypted) : this (input) {
    m_shift = shift;
    if (encrypted)
        m_field_4C |= 4;
}
```

#### SetSource

```csharp
public IBinaryStream SetSource (IBinaryStream source) {
    var prev = m_input;
    m_input = source;
    return prev;
}
```

#### GetObjectSchema

```csharp
public int GetObjectSchema () {
    int schema = m_objectSchema;

    return schema;
}
```

#### DeserializeRoot

```csharp
public CObject DeserializeRoot () {
    PopulateLoadArray();
    uint signature;
    var arc_class = LoadRioTypeCore (out signature);
    var obj = CreateObject (arc_class);
    MapObjectEntry (obj);
    if (RioSignature == signature)
        obj.Flags |= 0x80;
    else if (EncryptedSignature == signature)
        obj.Flags |= 0x180;
    DeserializeClassList (obj);
    obj.Deserialize (this);
    return obj;
}
```

#### ReadObject

```csharp
public CObject ReadObject (COceanNode node) {
    m_field_60 = false;
    var obj = CreateObject (node.Name);
    PopulateLoadArray();
    m_input.Position = ((long)node.Offset << m_shift);

    int f1 = ReadByte() & 3;
    int f2 = ReadByte();
    int f3 = ReadByte();
    int f4 = 0;
    switch (f2 >> 6)
    {
    case 0: f4 = f3 >> 6; break;
    case 1: f4 = f3 >> 2; break;
    case 2: f4 = (f3 & 0xFE) << 1 | (ReadByte() & 0xC0) << 1; break;
    case 3: f4 = (f3 & 0xFE) << 1 | (ReadByte() & 0xFE) << 6; break;
    }
    obj.Flags = node.Flags;
    MapObjectEntry (obj);
    if (2 == f1)
    {
        int flags = ReadUInt16();
        m_field_4C = (m_field_4C & 0xFFFF) | flags << 16;
    }
    else if (3 == f1)
    {
        int schema = ReadUInt16();
        int flags = ReadUInt16();
        m_field_4C = (m_field_4C & 0xFFFF) | flags << 16;
    }
    obj.Deserialize (this);
    return obj;
}
```

#### CreateObject

```csharp
CObject CreateObject (string class_name) {
    if (!s_classTable.ContainsKey (class_name))
        throw new InvalidFormatException (string.Format ("[RIO] Unknown class '{0}'", class_name));
    return s_classTable[class_name].CreateObject();
}
```

#### PopulateLoadArray

```csharp
void PopulateLoadArray () {
    m_LoadArray.Clear();
    m_LoadArray.Add (null);
    m_LoadArray.Add (this);
}
```

#### LoadRioTypeCore

```csharp
public string LoadRioTypeCore (out uint signature) {
    signature = m_input.ReadUInt32();
    if (!CoreSignatures.Contains (signature))
        throw new InvalidFormatException ("[RIO] invalid signature");
    int version = ReadUInt16();
    if (version >= 0x10 && version <= 0x3FFF)
    {
        Schema = version;
        if (version >= 0x11)
        {
            m_field_4C &= 0xFFFF;
            m_field_4C |= ReadUInt16() << 16;
        }
    }
    else
        m_input.Seek (-2, SeekOrigin.Current);
    if (EncryptedSignature == signature)
        m_field_4C |= 0xC;

    return ReadClass();
}
```

#### DeserializeClassList

```csharp
void DeserializeClassList (CObject root) {
    if (IsEncrypted && 0 != (root.Flags & 0x200))
        return;
    try
    {
        if (++m_depth > MaxRecursionDepth)
            throw new InvalidFormatException ("[RIO] deserialization recursion limit exceeded");
        int count = ReadCount();
        for (int i = 0; i < count; ++i)
        {
            if (IsEncrypted)
            {
                var node = CreateOceanEntry1 ("unrefix");
                DeserializeNode (node, node != null);
                if (node != null)
                    node.Parent = root;
            }
            else
            {
                m_field_50 = ReadString();
                m_field_54 = 0;
                var node = CreateOceanEntry2 (m_field_50);
                if (node != null)
                {
                    MapObjectEntry (node);
                    DeserializeNode (node);
                    node.Parent = root;
                }
                else
                {
                    node = FindObject (m_field_50) as COceanNode;
                    MapObjectEntry (node);
                    DeserializeNode (node, false);
                }
            }
        }
    }
    finally
    {
        --m_depth;
    }
}
```

#### DeserializeNode

```csharp
void DeserializeNode (COceanNode node, bool store_to_map = true) {
    int flags = ReadUInt16();
    string class_ref;
    switch (flags & 7)
    {
    case 0:
        if (0 != (flags & 0x8000))
            ReadByte();
        else
            ReadUInt16();
        class_ref = ReadClass();
        break;

    case 1:
        ReadInt32();
        class_ref = ReadCType();
        break;

    default:
            throw new InvalidFormatException();
    }
    node.ClassName = class_ref;
    if (node != null)
    {
        if (store_to_map)
            node.Flags = flags;
        if (0 != (flags & 8))
        {
            if (!store_to_map)
                node.Flags |= 8;
            int id1 = ReadInt32();
            int id2 = ReadInt32();
            if (IsEncrypted && store_to_map)
            {
                node.Flags |= 0x100;
                if (!m_OceanMap.ContainsKey (id1))
                    m_OceanMap[id1] = node;
            }
            if (node != null)
            {
                node.Offset = (uint)id1;
                node.Size   = (uint)id2;
                if ((long)node.Offset + node.Size > m_input.Length)
                {
                    node.Offset = DecodeOffset (id1);
                    node.Size = DecodeSize (id2);
                }
            }
        }
    }
    else
    {
        if (0 == (flags & 8))
            throw new InvalidFormatException();
        int id = ReadInt32();
        ReadInt32();
        if (!m_OceanMap.TryGetValue (id, out node))
            throw new InvalidFormatException();
    }
    DeserializeClassList (node);
}
```

#### ReadCType

```csharp
string ReadCType () {
    int c = ReadUInt16();
    switch (c)
    {
    case 0x1E57:
        return ReadClass();
    case 0x2D6B:
        return ReadBasicType();
    case 0x2F1A:
        return ReadBasicType();
    case 0x369E:
        if (m_field_54 > 0x13)
            return ReadMsgClass();
        else
            return ReadMessage();
    default:
        throw new InvalidFormatException();
    }
}
```

#### ReadMessage

```csharp
string ReadMessage () {
    int id = ReadUInt16();
    int cLen = ReadUInt16();
    if (id != -1 || cLen >= 0x400)
        throw new InvalidFormatException();
    var buffer = new byte[cLen];
    if (cLen != Read (buffer, 0, cLen))
        return null;
    var name = Encodings.cp932.GetString (buffer, 2, cLen-2);
    return GetRtcFromMessageName (name);
}
```

#### ReadBasicType

```csharp
string ReadBasicType () {
    ReadUInt16();
    int cLen = ReadUInt16();
    if (cLen >= 0x40 || cLen != Read (m_name_buf, 0, cLen))
        throw new InvalidFormatException();
    var name = Encodings.cp932.GetString (m_name_buf, 0, cLen);
    if (!s_basicTypeList.ContainsKey (name))
        throw new InvalidFormatException (string.Format ("[RIO] Unknown basic type '{0}'", name));
    return s_basicTypeList[name];
}
```

#### ReadMsgClass

```csharp
string ReadMsgClass () {
    int wTag = ReadUInt16();
    int obTag;
    if (0x7FFF == wTag)
        obTag = ReadInt32();
    else
        obTag = ((wTag & wClassTag) << 16) | (wTag & ~wClassTag);

    if (0 == (obTag & dwBigClassTag))
        throw new InvalidFormatException ("[RIO] invalid message class");
    if (0xFFFF == wTag)
    {
        throw new NotImplementedException();
    }
    else
    {
        throw new NotImplementedException();
    }
}
```

#### GetRtcFromMessageName

```csharp
string GetRtcFromMessageName (string name) {
    throw new NotImplementedException();
}
```

#### MapObjectEntry

```csharp
void MapObjectEntry (CObject node)
    m_LoadArray.Add (node);
}
```

#### FindObject

```csharp
CObject FindObject (string name) {
    throw new NotImplementedException();
}
```

#### CreateOceanEntry1

```csharp
COceanNode CreateOceanEntry1 (string name) {
    return new COceanNode (name);
}
```

#### CreateOceanEntry2

```csharp
COceanNode CreateOceanEntry2 (string name) {
    return new COceanNode (name);
}
```

#### CreateAnonymousRio

```csharp
COceanNode CreateAnonymousRio (string name) {
    throw new NotImplementedException();
}
```

#### ReadRioReference

```csharp
public CObject ReadRioReference (string base_ref) {
    if (!m_field_60)
    {
        m_field_60 = true;
        if (m_field_5C)
        {
            int count = ReadShortCount();
            for (int i = 0; i < count; ++i)
                MapObjectEntry (null);
        }
    }
    int tag;
    var class_ref = ReadClass (out tag);
    if (null == class_ref)
    {
        if (tag >= m_LoadArray.Count)
            throw new InvalidFormatException ("Bad class");
        return m_LoadArray[tag] as CObject;
    }

    COceanNode obj;
    int flags = ReadUInt16();
    if (0 != (flags & 0x40))
    {
        obj = CreateAnonymousRio (class_ref);
        MapObjectEntry (obj);
        return obj;
    }
    int id1 = 0, id2 = 0;
    string name = null;
    if (IsEncrypted)
    {
        id1 = ReadInt32();
        id2 = ReadInt32();
    }
    else
    {
        name = ReadString();
    }
    var rio = ReadRioReference ("CRio");
    if (null == rio)
        throw new InvalidFormatException();
    if (0 != (flags & 7))
        ReadInt32();
    else if (0 != (flags & 0x8000))
        ReadByte();
    else
        ReadUInt16();
    if (IsEncrypted)
    {
        obj = ReadEncryptedObject (rio, class_ref, flags, id1, id2);
        obj.Name = base_ref;
    }
    else
    {
        throw new NotImplementedException();
    }
    MapObjectEntry (obj);
    return obj;
}
```

#### ReadClass

```csharp
string ReadClass () {
    int tag;
    return ReadClass (out tag);
}
```

#### ReadClass

```csharp
string ReadClass (out int obTag) {
    int wTag = ReadUInt16();
    if (0x7FFF == wTag)
    {
        obTag = ReadInt32();
    }
    else
    {
        obTag = ((wTag & wClassTag) << 16) | (wTag & ~wClassTag);
    }
    if (0 == (obTag & dwBigClassTag))
    {
        return null;
    }

    string class_ref;
    if (0xFFFF == wTag)
    {
        uint schema = 0;
        if ((m_field_4C & 8) != 0)
            class_ref = LoadScrambledClass (out schema);
        else
            class_ref = LoadRuntimeClass (out schema);
        if (null == class_ref)
            throw new InvalidFormatException();
        m_objectSchema = (int)schema;

        m_LoadArray.Add (class_ref);
    }
    else
    {
        obTag &= 0x7FFFFFFF;
        if (0 == obTag || obTag >= m_LoadArray.Count)
            throw new InvalidFormatException ("Bad class");
        class_ref = (string)m_LoadArray[obTag];
    }
    return class_ref;
}
```

#### LoadRuntimeClass

```csharp
string LoadRuntimeClass (out uint schema) {
    schema = ReadUInt16();
    int nLen = ReadUInt16();

    if (nLen >= 0x40 || Read (m_name_buf, 0, nLen) != nLen)
        return null;
    return Encoding.ASCII.GetString (m_name_buf, 0, nLen);
}
```

#### LoadScrambledClass

```csharp
string LoadScrambledClass (out uint schema) {
    schema = ReadUInt16();
    int length = ReadByte();
    if (0xFF == length)
    {
        length = ReadUInt16();
    }
    if (length >= 0x100 || Read (m_name_buf, 0, length) != length)
        return null;

    return DecodeClassName (m_name_buf, length);
}
```

#### ReadEncryptedObject

```csharp
COceanNode ReadEncryptedObject (CObject rio, string class_ref, int flags, int id1, int id2) {
    COceanNode node;
    if (!m_OceanMap.TryGetValue (id1, out node))
        throw new InvalidFormatException();
    if (node != null)
    {
        node.Offset = DecodeOffset (id1);
        node.Size   = DecodeSize (id2);
    }
    return node;
}
```

#### ReadInt32

```csharp
public int ReadInt32 () {
    return m_input.ReadInt32();
}
```

#### ReadInt64

```csharp
public long ReadInt64 () {
    return m_input.ReadInt64();
}
```

#### ReadUInt16

```csharp
public ushort ReadUInt16 () {
    return m_input.ReadUInt16();
}
```

#### ReadByte

```csharp
public byte ReadByte () {
    return m_input.ReadUInt8();
}
```

#### Read

```csharp
public int Read (byte[] buffer, int offset, int count) {
    return m_input.Read (buffer, offset, count);
}
```

#### ReadBytes

```csharp
public byte[] ReadBytes (int count) {
    return m_input.ReadBytes (count);
}
```

#### ReadBool

```csharp
public bool ReadBool () {
    return m_input.ReadUInt8() != 0;
}
```

#### ReadString

```csharp
public string ReadString () {
    int nLength = ReadStringLength();
    if (0 == nLength)
        return "";
    if (nLength < 0)
        throw new InvalidFormatException();
    var buffer = m_input.ReadBytes (nLength);
    if (buffer.Length != nLength)
        throw new EndOfStreamException();
    return Encodings.cp932.GetString (buffer);
}
```

#### ReadCount

```csharp
public int ReadCount () {
    int count = ReadUInt16();
    if (count != 0xFFFF)
        return count;
    return ReadInt32();
}
```

#### ReadShortCount

```csharp
public int ReadShortCount () {
    int count = ReadByte();
    if (count != 0xFF)
        return count;
    return ReadUInt16();
}
```

#### ReadStringLength

```csharp
int ReadStringLength () {

    int length = ReadByte();
    if (length < 0xFF)
        return length;

    length = ReadUInt16();
    if (0xFFFE == length)
        throw new NotSupportedException ("[RIO] Unicode strings not supported");
    if (length < 0xFFFF)
        return length;

    return ReadInt32();
}
```

#### ReadEncrypted

```csharp
public byte[] ReadEncrypted (uint key) {
    uint size1 = m_input.ReadUInt32() ^ 0xC92E568B;
    uint size2 = m_input.ReadUInt32() ^ 0xC92E568F;
    size2 >>= 3;
    size1 = ~size1;
    if (size1 != size2)
        throw new InvalidFormatException ("Invalid encrypted chunk");
    var ici_data = new byte[size1];
    int dst = 0;
    while (dst < ici_data.Length)
    {
        ushort checksum = 0;
        int portion = Math.Min (0x20, ici_data.Length - dst);
        portion = m_input.Read (ici_data, dst, portion);
        for (int i = portion; i > 0; --i)
        {
            byte b = (byte)(ici_data[dst] ^ key);
            ici_data[dst++] = b;
            checksum += (ushort)(b * i);
            uint bit = key;
            bit = (bit >> 15) & 1;
            key = ~(bit + key*2 + 0xA3B376C9u);
        }
        if (portion < 0x20)
            break;
        ushort chunk_sum = m_input.ReadUInt16();
        if (chunk_sum != checksum)
            throw new InvalidFormatException ("Encrypted chunk checksum mismatch");
    }
    return ici_data;
}
```

#### DecodeOffset

```csharp
static uint DecodeOffset (int offset) {
    return (uint)offset - 0xA2FB6AD1;
}
```

#### DecodeSize

```csharp
static uint DecodeSize (int size) {
    uint a = (uint)size - 0xE7B5D9F8;
    uint b = a >> 13;
    return (a - (b & 0xFFF)) << 19 | b;
}
```

#### DecodeClassName

```csharp
static string DecodeClassName (byte[] enc, int length) {
    using (var output = new MemoryStream())
    using (var input = new MemoryStream (enc, 0, length))
    using (var bits = new LsbBitStream (input))
    {
        if (0 == bits.GetNextBit())
            output.WriteByte ((byte)'C');
        for (;;)
        {
            int b = bits.GetNextBit();
            if (-1 == b)
                break;
            int c;
            if (0 == b)
            {
                int idx = bits.GetBits (4);
                if (-1 == idx)
                    break;
                c = CharMap1[idx];
            }
            else if (bits.GetNextBit() != 0)
            {
                int idx = bits.GetBits (5);
                if (-1 == idx)
                    break;
                c = CharMap3[idx];
            }
            else
            {
                int idx = bits.GetBits (4);
                if (-1 == idx)
                    break;
                if (idx != 0)
                {
                    c = CharMap2[idx];
                }
                else
                {
                    c = bits.GetBits (8);
                    if (-1 == c)
                        break;
                }
            }
            output.WriteByte ((byte)c);
        }
        var buf = output.GetBuffer();
        return Encodings.cp932.GetString (buf, 0, (int)output.Length);
    }
}
```

### GameRes.Formats.Rugp.CObject

#### 状态与常量

```csharp
public int              Flags ;

public string           ClassName ;
```

#### Deserialize

```csharp
public abstract void Deserialize (CRioArchive arc) ;
```

### GameRes.Formats.Rugp.CStringArray

继承/接口：`CObject`, `IReadOnlyList<string>`。

#### 状态与常量

```csharp
string[]    m_data = new string[0] ;

public int Count { get { return m_data.Length; } }
```

#### SetSize

```csharp
public void SetSize (int count) {
    Array.Resize (ref m_data, count);
}
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    int count = arc.ReadCount();
    SetSize (count);
    for (int i = 0; i < count; ++i)
        m_data[i] = arc.ReadString();
}
```

### GameRes.Formats.Rugp.CPtrArray

继承/接口：`CObject`, `IReadOnlyList<CType>whereCType:CObject`, `new()`。

#### 状态与常量

```csharp
public CType[]  m_data = new CType[0] ;

public int Count { get { return m_data.Length; } }
```

#### SetSize

```csharp
public void SetSize (int count) {
    Array.Resize (ref m_data, count);
}
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    int count = arc.ReadCount();
    SetSize (count);
    for (int i = 0; i < count; ++i)
    {
        if (arc.ReadBool())
        {
            var obj = new CType();
            m_data[i] = obj;
            obj.Deserialize (arc);
        }
    }

}
```

### GameRes.Formats.Rugp.CInstallSource

继承/接口：`CObject`。

#### 状态与常量

```csharp
public ushort   Version ;

public int      field_14 ;

public int      field_18 ;

public string   RioName ;

public long     RioOffset ;

public long     RioSize ;

public int      field_A8 ;

public int      field_B0 ;

public byte[]   field_D4 ;
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    Version = arc.ReadUInt16();
    if (Version >= 7)
    {
        field_14 = arc.ReadInt32();
        field_18 = arc.ReadInt32();
        arc.ReadByte();
        arc.ReadString();
    }
    arc.ReadString();
    arc.ReadString();
    arc.ReadString();
    arc.ReadString();
    arc.ReadString();
    arc.ReadInt64();
    arc.ReadInt64();
    if (Version < 6)
    {
        arc.ReadInt32();
        arc.ReadInt32();
    }
    else
    {
        arc.ReadInt32();
    }
    RioName = arc.ReadString();
    RioOffset = arc.ReadInt64();
    RioSize = arc.ReadInt64();
    if (Version < 6)
    {
        arc.ReadInt64();
    }
    arc.ReadInt32();
    arc.ReadString();
    arc.ReadInt32();
    arc.ReadInt32();
    arc.ReadInt32();
    arc.ReadInt32();
    arc.ReadInt32();
    arc.ReadString();
    int count = arc.ReadCount();
    arc.ReadBytes (count*4);
    PrepareBuffer();
    arc.Read (field_D4, 0, field_D4.Length);
}
```

#### PrepareBuffer

```csharp
void PrepareBuffer () {
    field_B0 = (int)((RioSize + 0xFFFF) >> 16);
    field_A8 = 16;
    int length = (field_B0 + 7) >> 3;
    field_D4 = new byte[length];
}
```

### GameRes.Formats.Rugp.CObjectArcMan

继承/接口：`CObject`。

#### 状态与常量

```csharp
public int      Version ;

public string   Title ;

public CPtrArray<CInstallSource> ArcList = new CPtrArray<CInstallSource>() ;

public int      field_14 = 0x1873BE26 ;

public int      field_1C ;

public int      field_20 ;

public int      TocOffset ;

public int      TocSize ;

public int      field_38 = 0x14 ;

public string   RioFileName ;

public CStringArray field_80 = new CStringArray() ;

public int      field_98 = 0x30 ;
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    Version = arc.ReadInt32();
    field_14 = arc.ReadInt32();
    arc.ReadByte();
    arc.ReadByte();
    if (Version < 10)
    {
        field_1C = 0;
        field_20 = 0;
    }
    else
    {
        field_1C = arc.ReadInt32();
        field_20 = arc.ReadInt32();
    }
    arc.ReadInt32();
    arc.ReadInt32();
    arc.ReadInt32();
    if (Version >= 6)
    {
        TocOffset = arc.ReadInt32();
        TocSize   = arc.ReadInt32();
        arc.ReadInt32();
    }
    if (Version >= 8)
        field_38 = arc.ReadInt32();
    Title = arc.ReadString();
    arc.ReadInt32();
    arc.ReadString();
    arc.ReadInt32();
    arc.ReadString();
    arc.ReadString();
    arc.ReadString();
    arc.ReadInt32();
    arc.ReadString();
    field_80.Deserialize (arc);
    arc.ReadInt32();
    if (Version >= 9)
        RioFileName = arc.ReadString();
    if (Version >= 7)
        arc.ReadString();
    if (Version >= 5)
        field_98 = arc.ReadInt32();
    ArcList.Deserialize (arc);
    for (int i = 0; i < ArcList.Count; ++i)
    {
        var entry = ArcList[i];
        if (entry != null)
        {
            entry.field_14 = field_1C;
            entry.field_18 = field_20;
        }
    }
}
```

### GameRes.Formats.Rugp.CrelicUnitedGameProject

继承/接口：`CObject`。

#### 状态与常量

```csharp
public int          Version ;

public CObject      field_08 ;

public CObject      field_0C ;

public CObject      field_10 ;

public CObject      field_14 ;

public CObject      field_18 ;

public CObject      field_1C ;

public CObject      field_24 ;

public CObject      field_28 ;

public CObject      field_2C ;

public CObject      field_30 ;

public CUnknown1    field_34 = new CUnknown1() ;

public CObject      field_38 ;

internal const uint RioKey = 0x7E6B8CE2 ;
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    if (arc.IsEncrypted)
    {
        var data = arc.ReadEncrypted (RioKey);
        using (var input = new BinMemoryStream (data))
        {
            var prev_source = arc.SetSource (input);
            try
            {
                ReadRelic (arc);
            }
            finally
            {
                arc.SetSource (prev_source);
            }
        }
    }
    else
        ReadRelic (arc);
}
```

#### ReadRelic

```csharp
void ReadRelic (CRioArchive arc) {
    try
    {
        Version = arc.ReadInt32();
        if (Version >= 0x24)
        {
            field_24 = arc.ReadRioReference ("CDatabaseBase");
            field_28 = arc.ReadRioReference ("CDatabaseBase");
            field_10 = arc.ReadRioReference ("CBoxOcean");
            field_14 = arc.ReadRioReference ("CObjectOcean");
            field_18 = arc.ReadRioReference ("CObjectOcean");
            field_0C = arc.ReadRioReference ("CProcessOcean");
            if (Version >= 0x25)
                field_30 = arc.ReadRioReference ("CStdb");
            if (Version >= 0x26)
                field_2C = arc.ReadRioReference ("CRio");
            if (Version >= 0x27)
                field_1C = arc.ReadRioReference ("CRio");
            if (Version >= 0x29)
                field_38 = arc.ReadRioReference ("CRio");
            field_34.Deserialize (arc);
            if (Version >= 0x28)
                field_08 = arc.ReadRioReference ("CRio");
        }
        else if (Version >= 0x20)
        {
            field_0C = arc.ReadRioReference ("CProcessOcean");
            field_10 = arc.ReadRioReference ("CBoxOcean");
            field_14 = arc.ReadRioReference ("CObjectOcean");
            field_18 = arc.ReadRioReference ("CObjectOcean");
            field_1C = arc.ReadRioReference ("CSoundManEx");
            if (Version >= 0x23)
                field_24 = arc.ReadRioReference ("CDatabaseBase");
            if (Version >= 0x22)
                field_28 = arc.ReadRioReference ("CDatabaseBase");
            if (Version >= 0x21)
                field_34.Deserialize (arc);
        }
        else
            throw new NotSupportedException (string.Format ("rUGP schema {0} not supported", Version));
    }
    catch {  }
}
```

### GameRes.Formats.Rugp.CUnknown1

继承/接口：`CObject`。

#### 状态与常量

```csharp
public int          Version = 0 ;

public string       field_04 ;

public string       field_08 ;

public string       field_0C ;

public string       field_14 ;

public int          field_18 = 1000 ;

public string       field_1C ;

public string       field_10 ;

public int          field_20 = 1 ;

public int          field_24 = 1 ;

public byte[]       field_28 ;

public int          field_38 ;

public string       field_3C ;

public string       field_40 ;

public string       field_44 ;

public string       field_48 ;

public string       field_4C ;

public string       field_50 ;
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    Version = arc.ReadInt32();
    if (Version >= 2)
        field_04 = arc.ReadString();
    field_08 = arc.ReadString();
    field_0C = arc.ReadString();
    field_14 = arc.ReadString();
    field_1C = arc.ReadString();
    field_18 = arc.ReadInt32();
    if (0 == Version)
       return;
    if (Version >= 2)
    {
        field_28 = arc.ReadBytes (16);
        field_38 = arc.ReadInt32();
    }
    field_3C = arc.ReadString();
    field_40 = arc.ReadString();
    if (Version >= 3)
        field_44 = arc.ReadString();
    if (Version >= 4)
    {
        field_10 = arc.ReadString();
        field_20 = arc.ReadInt32();
    }
    if (Version >= 5)
    {
        field_24 = arc.ReadInt32();
    }
    else if (Version >= 2)
    {
        if (field_28.ToUInt16 (0) < 0x7D3)
            field_24 = 2;
        else
            field_24 = 1;
    }
    if (Version >= 6)
    {
        field_48 = arc.ReadString();
        field_4C = arc.ReadString();
        field_50 = arc.ReadString();
    }
}
```

### GameRes.Formats.Rugp.CStdb

继承/接口：`CObject`。

#### 状态与常量

```csharp
public string   field_0C ;
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    field_0C = arc.ReadString();
}
```

### GameRes.Formats.Rugp.CBoxOcean

继承/接口：`CObject`。

#### 状态与常量

```csharp
public CObject          field_10 ;

public CObject          field_14 ;

public List<CObject>    field_18 = new List<CObject>() ;

public List<string>     field_118 = new List<string>() ;

public CObject          field_198 ;

public List<CObject>    m_box_list = new List<CObject>() ;

static CObject          static_cui = null ;
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    field_10 = arc.ReadRioReference ("CFrameBuffer");
    int schema = arc.GetObjectSchema();
    if (schema < 3)
    {
        for (int i = 0; i < 32; ++i)
        {
            var box = arc.ReadRioReference ("CBox");
            m_box_list.Add (box);
        }
    }
    if (schema >= 2)
    {
        field_14 = arc.ReadRioReference ("CSbm");
        if (schema < 6)
        {
            field_18.Add (arc.ReadRioReference ("CSbm"));
        }
        else
        {
            int ref_count = 15;
            int str_count = 0;
            if (schema >= 7)
            {
                ref_count = 32;
                str_count = 32;
            }
            for (int i = 0; i < ref_count; ++i)
            {
                field_18.Add (arc.ReadRioReference ("CSbm"));
            }
            for (int i = 0; i < str_count; ++i)
            {
                field_118.Add (arc.ReadString());
            }
        }
        field_198 = arc.ReadRioReference ("CUnitedMenu");
        if (schema >= 4)
        {
            ReadCui (arc);
            if (schema >= 5)
            {
                var cui = arc.ReadRioReference ("CUI");
                if (cui != static_cui)
                {
                    ReadCui (arc);
                }
            }
        }
    }
}
```

#### ReadCui

```csharp
void ReadCui (CRioArchive arc) {
    while (arc.ReadByte() != 0)
    {
        var cui = arc.ReadRioReference ("CUI");
    }
}
```

### GameRes.Formats.Rugp.CObjectOcean

继承/接口：`CObject`。

### GameRes.Formats.Rugp.CRio

继承/接口：`CObject`。

### GameRes.Formats.Rugp.COceanNode

继承/接口：`CObject`。

#### 状态与常量

```csharp
public string   Name ;

public CObject  Parent ;

public uint     Offset ;

public uint     Size ;
```

#### COceanNode

```csharp
public COceanNode (string name) {
    Name = name;
}
```

#### Deserialize

```csharp
public override void Deserialize (CRioArchive arc) {
    throw new NotImplementedException ("COceanNode.Deserialize not impelemented");
}
```

#### GetPathName

```csharp
public string GetPathName () {
    return string.Join ("/", TraversePath().Reverse());
}
```

#### TraversePath

```csharp
private IEnumerable<string> TraversePath () {
    COceanNode node = this;
    while (node != null && node.ClassName != null && !string.IsNullOrEmpty (node.Name))
    {
        yield return node.Name;
        node = node.Parent as COceanNode;
    }
}
```

### GameRes.Formats.Rugp.CObjectFactory

继承/接口：`IObjectFactorywhereCType:CObject`, `new()`。

#### CreateObject

```csharp
public CObject CreateObject () {
    return new CType();
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/rUGP/ArcRIO.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
