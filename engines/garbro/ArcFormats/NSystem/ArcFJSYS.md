# NSystem / ArcFJSYS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FJSYS` / `GameRes.Formats.NSystem.FjsysOpener` | `` | `464a5359` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `FjsysOpener.TryOpen` | `if (file.View.ReadByte (4) != 'S')` |
| `FjsysOpener.TryOpen` | `uint names_size = file.View.ReadUInt32 (0xC);` |
| `FjsysOpener.TryOpen` | `int count = file.View.ReadInt32 (0x10);` |
| `FjsysOpener.TryOpen` | `var names = file.View.ReadBytes (index_offset + index_size, names_size);` |
| `FjsysOpener.TryOpen` | `var name_offset = file.View.ReadInt32 (index_offset);` |
| `FjsysOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+4);` |
| `FjsysOpener.TryOpen` | `entry.Offset = file.View.ReadInt64 (index_offset+8);` |
| `FjsysOpener.OpenEntry` | `\|\| arc.File.View.AsciiEqual (entry.Offset, "MSCENARIO FILE  "))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NSystem.MsdArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly string Key ;
```

#### MsdArchive

```csharp
public MsdArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, string key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.NSystem.FjsysOpener

继承/接口：`ArchiveFormat`。

#### FjsysOpener

```csharp
public FjsysOpener () {
    Extensions = new string[] { "" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadByte (4) != 'S')
        return null;
    uint names_size = file.View.ReadUInt32 (0xC);
    int count = file.View.ReadInt32 (0x10);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 0x54;
    uint index_size = (uint)count * 0x10;
    var names = file.View.ReadBytes (index_offset + index_size, names_size);

    var dir = new List<Entry> (count);
    bool has_scripts = false;
    for (int i = 0; i < count; ++i)
    {
        var name_offset = file.View.ReadInt32 (index_offset);
        var name = Binary.GetCString (names, name_offset);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = file.View.ReadUInt32 (index_offset+4);
        entry.Offset = file.View.ReadInt64 (index_offset+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        has_scripts = has_scripts || name.HasExtension (".msd");
        dir.Add (entry);
        index_offset += 0x10;
    }
    if (has_scripts)
    {
        var password = QueryPassword (file.Name);
        if (!string.IsNullOrEmpty (password))
            return new MsdArchive (file, this, dir, password);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var msarc = arc as MsdArchive;
    if (null == msarc || string.IsNullOrEmpty (msarc.Key)
        || !entry.Name.HasExtension (".msd")
        || arc.File.View.AsciiEqual (entry.Offset, "MSCENARIO FILE  "))
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new InputCryptoStream (input, new MsdTransform (msarc.Key));
}
```

#### QueryPassword

```csharp
string QueryPassword (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title) && KnownPasswords.ContainsKey (title))
        return KnownPasswords[title];
    var options = Query<FjsysOptions> (arcStrings.FJSYSNotice);
    return options.MsdPassword;
}
```

### GameRes.Formats.NSystem.MsdTransform

继承/接口：`ICryptoTransform`。

#### 状态与常量

```csharp
const int BlockSize = 0x20 ;

string          m_key ;

MD5             m_md5 ;

StringBuilder   m_hash_str ;

int             m_block_num ;

public bool          CanReuseTransform { get { return false; } }

public bool CanTransformMultipleBlocks { get { return true; } }

public int              InputBlockSize { get { return BlockSize; } }

public int             OutputBlockSize { get { return BlockSize; } }

bool _disposed = false ;
```

#### MsdTransform

```csharp
public MsdTransform (string key) {
    m_key = key;
    m_md5 = MD5.Create();
    m_hash_str = new StringBuilder (BlockSize);
    m_block_num = 0;
}
```

#### TransformBlock

```csharp
public int TransformBlock (byte[] inputBuffer, int inputOffset, int inputCount,
                           byte[] outputBuffer, int outputOffset) {
    int block_count = inputCount / BlockSize;
    for (int i = 0; i < block_count; ++i)
    {
        DoTransform (inputBuffer, inputOffset, BlockSize, outputBuffer, outputOffset);
        inputOffset += BlockSize;
        outputOffset += BlockSize;
    }
    return inputCount;
}
```

#### TransformFinalBlock

```csharp
public byte[] TransformFinalBlock (byte[] inputBuffer, int inputOffset, int inputCount) {
    byte[] outputBuffer = new byte[inputCount];
    DoTransform (inputBuffer, inputOffset, inputCount, outputBuffer, 0);
    return outputBuffer;
}
```

#### DoTransform

```csharp
void DoTransform (byte[] input, int src, int count, byte[] output, int dst) {
    string chunk_key_str = m_key + m_block_num.ToString();
    ++m_block_num;
    var chunk_key = Encodings.cp932.GetBytes (chunk_key_str);
    var hash = m_md5.ComputeHash (chunk_key);
    m_hash_str.Clear();
    for (int j = 0; j < hash.Length; ++j)
        m_hash_str.AppendFormat ("{0:x2}", hash[j]);
    count = Math.Min (m_hash_str.Length, count);
    for (int k = 0; k < count; ++k)
        output[dst++] = (byte)(input[src++] ^ m_hash_str[k]);
}
```

### GameRes.Formats.NSystem.FjsysOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public string MsdPassword ;
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/NSystem/ArcFJSYS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
