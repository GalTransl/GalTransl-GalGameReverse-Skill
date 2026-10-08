# Selene / ArcKCAP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `KCAP` / `GameRes.Formats.Selene.PackOpener` | `pack` | `4b434150` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PackOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `PackOpener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x40);` |
| `PackOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x48);` |
| `PackOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x4C);` |
| `PackOpener.TryOpen` | `entry.Encrypted = 0 != file.View.ReadUInt32 (index_offset+0x50);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Selene.SeleneArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte[] KeyTable ;
```

#### SeleneArchive

```csharp
public SeleneArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte[] key)
    : base (arc, impl, dir) {
    KeyTable = key;
}
```

### GameRes.Formats.Selene.KcapEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public bool Encrypted ;
```

### GameRes.Formats.Selene.KcapOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public string PassPhrase { get; set; }
```

### GameRes.Formats.Selene.PackOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static private string DefaultPassPhrase = "Selene.Default.Password" ;

static KcapScheme DefaultScheme = new KcapScheme { KnownSchemes = new Dictionary<string,string>() }
```

#### PackOpener

```csharp
public PackOpener () {
    Extensions = new string[] { "pack" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    uint index_size = (uint)count * 0x54u;
    if (index_size > file.View.Reserve (8, index_size))
        return null;
    long index_offset = 8;
    var dir = new List<Entry> (count);
    bool encrypted = false;
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x40);
        var entry = Create<KcapEntry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x48);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x4C);
        entry.Encrypted = 0 != file.View.ReadUInt32 (index_offset+0x50);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        encrypted = encrypted || entry.Encrypted;
        dir.Add (entry);
        index_offset += 0x54;
    }
    if (!encrypted)
        return new ArcFile (file, this, dir);
    var options = Query<KcapOptions> (arcStrings.ArcEncryptedNotice);
    var key = CreateKeyTable (options.PassPhrase);
    return new SeleneArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var kpa = arc as SeleneArchive;
    var kpe = entry as KcapEntry;
    if (null == kpa || null == kpe || !kpe.Encrypted)
        return input;
    return new InputCryptoStream (input, new KcapTransform(kpa.KeyTable));
}
```

#### GetPassPhrase

```csharp
public static string GetPassPhrase (string title) {
    string pass;
    if (string.IsNullOrEmpty (title) || !KnownSchemes.TryGetValue (title, out pass))
        return "";
    return pass;
}
```

#### CreateKeyTable

```csharp
static private byte[] CreateKeyTable (string pass) {
    if (pass.Length < 8)
        pass = DefaultPassPhrase;
    int pass_len = pass.Length;
    uint seed = PasskeyHash (pass);
    var rng = new KeyTableGenerator ((int)seed);
    byte[] table = new byte[0x10000];
    for (int i = 0; i < table.Length; ++i)
    {
        int key = rng.Rand();
        table[i] = (byte)(pass[i % pass_len] ^ (key >> 16));
    }
    return table;
}
```

#### PasskeyHash

```csharp
static uint PasskeyHash (string pass) {
    var bytes = Encodings.cp932.GetBytes (pass);
    return Crc32.Compute (bytes, 0, bytes.Length);
}
```

### GameRes.Formats.Selene.PackOpener.KeyTableGenerator

#### 状态与常量

```csharp
const int   StateLength     = 624 ;

const int   StateM          = 397 ;

const int   MatrixA         = -1727483681 ;

const int   TemperingMaskB  = -1658038656 ;

const int   TemperingMaskC  = -272236544 ;

private int[]   m_table = new int[StateLength] ;

private int     m_pos ;

private static int[] mag01 = new int[2] { 0, MatrixA }
```

#### KeyTableGenerator

```csharp
public KeyTableGenerator (int seed = 0) {
    SRand (seed);
}
```

#### SRand

```csharp
public void SRand (int seed) {
    m_table[0] = seed;
    for (int i = 1; i < StateLength; ++i)
        m_table[i] = i + 0x6C078965 * (m_table[i-1] ^ (m_table[i-1] >> 30));
    m_pos = StateLength;
}
```

#### Rand

```csharp
public int Rand () {
    if (m_pos >= StateLength)
    {
        int i;
        for (i = 0; i < StateLength - StateM; ++i)
        {
            int x = m_table[i] ^ m_table[i+1];
            m_table[i] = m_table[i + StateM] ^ mag01[(m_table[i] ^ x) & 1]
                       ^ ((m_table[i] ^ x & 0x7FFFFFFF) >> 1);
        }
        for (; i < StateLength - 1; ++i)
        {
            int x = m_table[i] ^ m_table[i + 1];
            m_table[i] = m_table[i + StateM - StateLength] ^ mag01[(m_table[i] ^ x) & 1]
                       ^ ((m_table[i] ^ x & 0x7FFFFFFF) >> 1);
        }
        int z = m_table[StateLength - 1] ^ (m_table[0] ^ m_table[StateLength-1]) & 0x7FFFFFFF;
        m_table[StateLength - 1] = m_table[StateM-1] ^ (z >> 1) ^ mag01[z & 1];
        m_pos = 0;
    }
    int y = m_table[m_pos++];
    y ^= y >> 11;
    y ^= (y << 7)  & TemperingMaskB;
    y ^= (y << 15) & TemperingMaskC;
    y ^= y >> 18;
    return y;
}
```

### GameRes.Formats.Selene.PackOpener.KcapTransform

继承/接口：`ICryptoTransform`。

#### 状态与常量

```csharp
private readonly byte[] KeyTable ;

public bool          CanReuseTransform { get { return true; } }

public bool CanTransformMultipleBlocks { get { return false; } }

public int              InputBlockSize { get { return KeyTable.Length; } }

public int             OutputBlockSize { get { return KeyTable.Length; } }
```

#### KcapTransform

```csharp
public KcapTransform (byte[] key_table) {
    KeyTable = key_table;
}
```

#### TransformBlock

```csharp
public int TransformBlock (byte[] inputBuffer, int inputOffset, int inputCount,
                        byte[] outputBuffer, int outputOffset) {
    for (int i = 0; i < inputCount; ++i)
    {
        outputBuffer[outputOffset++] = (byte)(inputBuffer[inputOffset+i]^KeyTable[i]);
    }
    return inputCount;
}
```

#### TransformFinalBlock

```csharp
public byte[] TransformFinalBlock (byte[] inputBuffer, int inputOffset, int inputCount) {
    byte[] outputBuffer = new byte[inputCount];
    TransformBlock (inputBuffer, inputOffset, inputCount, outputBuffer, 0);
    return outputBuffer;
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Selene/ArcKCAP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
