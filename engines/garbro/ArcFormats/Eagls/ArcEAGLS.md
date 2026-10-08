# Eagls / ArcEAGLS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/EAGLS` / `GameRes.Formats.Eagls.PakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `long first_offset = LittleEndian.ToUInt32 (index, name_size);` |
| `PakOpener.TryOpen` | `entry.Offset = LittleEndian.ToInt64 (index, index_offset) - first_offset;` |
| `PakOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (index, index_offset+8);` |
| `PakOpener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset) - first_offset;` |
| `PakOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `PakOpener.DecryptIndex` | `rng.SRand (view.ReadInt32 (idx_size));` |
| `PakOpener.DetectEncryptionScheme` | `int signature = (file.View.ReadInt32 (first_entry.Offset) >> 8) & 0xFFFF;` |
| `PakOpener.DetectEncryptionScheme` | `byte seed = file.View.ReadByte (first_entry.Offset+first_entry.Size-1);` |
| `EaglsArchive.DecryptEntry` | `byte[] input = File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Eagls.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal static readonly string IndexKey = "1qaz2wsx3edc4rfv5tgb6yhn7ujm8ik,9ol.0p;/-@:^[]" ;

internal static readonly byte[] EaglsKey  = Encoding.ASCII.GetBytes ("EAGLS_SYSTEM") ;

internal static readonly byte[] AdvSysKey = Encoding.ASCII.GetBytes ("ADVSYS") ;
```

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.Name.HasExtension (".idx"))
        return null;
    string idx_name = Path.ChangeExtension (file.Name, ".idx");
    if (!VFS.FileExists (idx_name))
        return null;
    var idx_entry = VFS.FindFile (idx_name);
    if (idx_entry.Size > 0xfffff || idx_entry.Size < 10000)
        return null;

    byte[] index;
    using (var idx = VFS.OpenView (idx_entry))
        index = DecryptIndex (idx);
    int index_offset = 0;
    int entry_size = index.Length / 10000;
    if (entry_size > 40)
        entry_size = 40;
    bool long_offsets = 40 == entry_size;
    int name_size = long_offsets ? 0x18 : 0x14;
    long first_offset = LittleEndian.ToUInt32 (index, name_size);
    bool has_scripts = false;
    var dir = new List<Entry>();
    while (index_offset < index.Length)
    {
        if (0 == index[index_offset])
            break;
        var name = Binary.GetCString (index, index_offset, name_size);
        index_offset += name_size;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        if (name.HasExtension ("dat"))
        {
            entry.Type = "script";
            has_scripts = true;
        }
        if (long_offsets)
        {
            entry.Offset = LittleEndian.ToInt64 (index, index_offset) - first_offset;
            entry.Size   = LittleEndian.ToUInt32 (index, index_offset+8);
            index_offset += 0x10;
        }
        else
        {
            entry.Offset = LittleEndian.ToUInt32 (index, index_offset) - first_offset;
            entry.Size   = LittleEndian.ToUInt32 (index, index_offset+4);
            index_offset += 8;
        }
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;
    if (dir[0].Name.HasExtension ("gr"))
    {
        var rng = DetectEncryptionScheme (file, dir[0]);
        if (rng != null)
            return new EaglsArchive (file, this, dir, new CgEncryption (rng));
    }
    else if (has_scripts)
    {
        var enc = QueryEncryption();
        if (enc != null)
            return new EaglsArchive (file, this, dir, enc);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var earc = arc as EaglsArchive;
    if (null == earc || !entry.Name.HasAnyOfExtensions ("dat", "gr"))
        return arc.File.CreateStream (entry.Offset, entry.Size);

    return earc.DecryptEntry (entry);
}
```

#### DecryptIndex

```csharp
byte[] DecryptIndex (ArcView idx) {
    int idx_size = (int)idx.MaxOffset-4;
    byte[] output = new byte[idx_size];
    using (var view = idx.CreateViewAccessor (0, (uint)idx.MaxOffset))
    unsafe
    {
        var rng = new CRuntimeRandomGenerator();
        rng.SRand (view.ReadInt32 (idx_size));
        byte* ptr = view.GetPointer (0);
        try
        {
            for (int i = 0; i < idx_size; ++i)
            {
                output[i] = (byte)(ptr[i] ^ IndexKey[rng.Rand() % IndexKey.Length]);
            }
            return output;
        }
        finally
        {
            view.SafeMemoryMappedViewHandle.ReleasePointer();
        }
    }
}
```

#### DetectEncryptionScheme

```csharp
IRandomGenerator DetectEncryptionScheme (ArcView file, Entry first_entry) {
    int signature = (file.View.ReadInt32 (first_entry.Offset) >> 8) & 0xFFFF;
    if (0x4D42 == signature)
        return null;
    byte seed = file.View.ReadByte (first_entry.Offset+first_entry.Size-1);
    IRandomGenerator[] rng_list = {
        new LehmerRandomGenerator(),
        new CRuntimeRandomGenerator(),
    };
    foreach (var rng in rng_list)
    {
        rng.SRand (seed);
        rng.Rand();
        int test = signature;
        test ^= EaglsKey[rng.Rand() % EaglsKey.Length];
        test ^= EaglsKey[rng.Rand() % EaglsKey.Length] << 8;

        if (0x4D42 == test)
            return rng;
    }
    throw new UnknownEncryptionScheme();
}
```

#### QueryEncryption

```csharp
IEntryEncryption QueryEncryption () {
    var options = Query<EaglsOptions> (arcStrings.ArcEncryptedNotice);
    return options.Encryption;
}
```

### GameRes.Formats.Eagls.EaglsOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public IEntryEncryption Encryption ;
```

### GameRes.Formats.Eagls.CRuntimeRandomGenerator

继承/接口：`IRandomGenerator`。

#### 状态与常量

```csharp
uint m_seed ;
```

#### SRand

```csharp
public void SRand (int seed) {
    m_seed = (uint)seed;
}
```

#### Rand

```csharp
public int Rand () {
    m_seed = m_seed * 214013u + 2531011u;
    return (int)(m_seed >> 16) & 0x7FFF;
}
```

### GameRes.Formats.Eagls.LehmerRandomGenerator

继承/接口：`IRandomGenerator`。

#### 状态与常量

```csharp
int m_seed ;

const int A = 48271 ;

const int Q = 44488 ;

const int R = 3399 ;

const int M = 2147483647 ;
```

#### SRand

```csharp
public void SRand (int seed) {
    m_seed = seed ^ 123459876;
}
```

#### Rand

```csharp
public int Rand () {
    m_seed = A * (m_seed % Q) - R * (m_seed / Q);
    if (m_seed < 0)
        m_seed += M;
    return (int)(m_seed * 4.656612875245797e-10 * 256);
}
```

### GameRes.Formats.Eagls.CgEncryption

继承/接口：`IEntryEncryption`。

#### 状态与常量

```csharp
readonly byte[] Key = PakOpener.EaglsKey ;

readonly IRandomGenerator m_rng ;
```

#### CgEncryption

```csharp
public CgEncryption (IRandomGenerator rng) {
    m_rng = rng;
}
```

#### Decrypt

```csharp
public void Decrypt (byte[] data) {
    m_rng.SRand (data[data.Length-1]);
    int limit = Math.Min (data.Length-1, 0x174b);
    for (int i = 0; i < limit; ++i)
    {
        data[i] ^= (byte)Key[m_rng.Rand() % Key.Length];
    }
}
```

### GameRes.Formats.Eagls.EaglsArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
readonly IEntryEncryption Encryption ;
```

#### EaglsArchive

```csharp
public EaglsArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IEntryEncryption enc)
    : base (arc, impl, dir) {
    Encryption = enc;
}
```

#### DecryptEntry

```csharp
public Stream DecryptEntry (Entry entry) {
    byte[] input = File.View.ReadBytes (entry.Offset, entry.Size);
    Encryption.Decrypt (input);
    return new BinMemoryStream (input, entry.Name);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Eagls/ArcEAGLS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
