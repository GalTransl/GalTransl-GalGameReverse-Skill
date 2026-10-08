# CatSystem / ArcINT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `INT` / `GameRes.Formats.CatSystem.IntOpener` | `int` | `4b494600` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `IntOpener.TryOpen` | `int entry_count = file.View.ReadInt32 (4);` |
| `IntOpener.TryOpen` | `if (file.View.AsciiEqual (8, "__key__.dat\x00"))` |
| `IntOpener.TryOpen` | `string name = file.View.ReadString (current_offset, name_length);` |
| `IntOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (current_offset);` |
| `IntOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (current_offset+4);` |
| `IntOpener.OpenEncrypted` | `uint seed = file.View.ReadUInt32 (current_offset+0x44);` |
| `IntOpener.OpenEncrypted` | `uint offset = file.View.ReadUInt32 (current_offset+0x40) + (uint)i;` |
| `IntOpener.OpenEncrypted` | `uint size   = file.View.ReadUInt32 (current_offset+0x44);` |
| `IntOpener.OpenEncryptedEntry` | `byte[] data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CatSystem.FrontwingArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly Blowfish Encryption ;
```

#### FrontwingArchive

```csharp
public FrontwingArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, Blowfish cipher)
    : base (arc, impl, dir) {
    Encryption = cipher;
}
```

### GameRes.Formats.CatSystem.IntOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public IntEncryptionInfo EncryptionInfo { get; set; }
```

### GameRes.Formats.CatSystem.IntOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] NameSizes = { 0x20, 0x40 }

static IntScheme DefaultScheme = new IntScheme { KnownKeys = new Dictionary<string, KeyData>() }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int entry_count = file.View.ReadInt32 (4);
    if (!IsSaneCount (entry_count))
        return null;
    if (file.View.AsciiEqual (8, "__key__.dat\x00"))
    {
        uint? key = QueryEncryptionInfo (file.Name);
        if (null == key)
            throw new UnknownEncryptionScheme();
        return OpenEncrypted (file, entry_count, key.Value);
    }

    var dir = new List<Entry> (entry_count);
    foreach (var name_length in NameSizes)
    {
        try
        {
            long current_offset = 8;
            for (int i = 0; i < entry_count; ++i)
            {
                string name = file.View.ReadString (current_offset, name_length);
                if (0 == name.Length)
                {
                    dir.Clear();
                    break;
                }
                var entry = FormatCatalog.Instance.Create<Entry> (name);
                current_offset += name_length;
                entry.Offset = file.View.ReadUInt32 (current_offset);
                entry.Size   = file.View.ReadUInt32 (current_offset+4);
                if (entry.Offset <= current_offset || !entry.CheckPlacement (file.MaxOffset))
                {
                    dir.Clear();
                    break;
                }
                dir.Add (entry);
                current_offset += 8;
            }
            if (dir.Count > 0)
                return new ArcFile (file, this, dir);
        }
        catch {  }
    }
    return null;
}
```

#### OpenEncrypted

```csharp
private ArcFile OpenEncrypted (ArcView file, int entry_count, uint main_key) {
    if (1 == entry_count)
        return null;
    long current_offset = 8;

    uint seed = file.View.ReadUInt32 (current_offset+0x44);
    var twister = new MersenneTwister (seed);
    byte[] blowfish_key = BitConverter.GetBytes (twister.Rand());
    if (!BitConverter.IsLittleEndian)
        Array.Reverse (blowfish_key);

    var blowfish = new Blowfish (blowfish_key);
    var dir = new List<Entry> (entry_count-1);
    byte[] name_buffer = new byte[0x40];
    for (int i = 1; i < entry_count; ++i)
    {
        current_offset += 0x48;
        file.View.Read (current_offset, name_buffer, 0, 0x40);
        uint offset = file.View.ReadUInt32 (current_offset+0x40) + (uint)i;
        uint size   = file.View.ReadUInt32 (current_offset+0x44);
        blowfish.Decipher (ref offset, ref size);
        twister.SRand (main_key + (uint)i);
        uint name_key = twister.Rand();
        string name = DecipherName (name_buffer, name_key);

        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = offset;
        entry.Size   = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return new FrontwingArchive (file, this, dir, blowfish);
}
```

#### OpenEncryptedEntry

```csharp
private Stream OpenEncryptedEntry (FrontwingArchive arc, Entry entry) {
    byte[] data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    arc.Encryption.Decipher (data, data.Length/8*8);
    return new BinMemoryStream (data, entry.Name);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (arc is FrontwingArchive)
        return OpenEncryptedEntry (arc as FrontwingArchive, entry);
    else
        return base.OpenEntry (arc, entry);
}
```

#### DecipherName

```csharp
public string DecipherName (byte[] name, uint key) {
    string alphabet = "zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA";
    int k = (byte)((key >> 24) + (key >> 16) + (key >> 8) + key);
    int i;
    for (i = 0; i < name.Length && name[i] != 0; ++i)
    {
        int j = alphabet.IndexOf ((char)name[i]);
        if (j != -1)
        {
            j -= k % 0x34;
            if (j < 0) j += 0x34;
            name[i] = (byte)alphabet[0x33-j];
        }
        ++k;
    }
    return Encodings.cp932.GetString (name, 0, i);
}
```

#### QueryEncryptionInfo

```csharp
uint? QueryEncryptionInfo (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title) && KnownSchemes.ContainsKey (title))
        return KnownSchemes[title].Key;
    var options = Query<IntOptions> (arcStrings.INTNotice);
    return options.EncryptionInfo.GetKey();
}
```

#### GetPassFromExe

```csharp
public static string GetPassFromExe (string filename) {
    using (var exe = new ExeFile.ResourceAccessor (filename))
    {
        var code = exe.GetResource ("DATA", "V_CODE2");
        if (null == code || code.Length < 8)
            return null;
        var key = exe.GetResource ("KEY", "KEY_CODE");
        if (null != key)
        {
            for (int i = 0; i < key.Length; ++i)
                key[i] ^= 0xCD;
        }
        else
        {
            key = Encoding.ASCII.GetBytes ("windmill");
        }
        var blowfish = new Blowfish (key);
        blowfish.Decipher (code, code.Length/8*8);
        int length = Array.IndexOf<byte> (code, 0);
        if (-1 == length)
            length = code.Length;
        return Encodings.cp932.GetString (code, 0, length);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/Blowfish.cs](../Blowfish.md)：本页引用的随包算法资料。
- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/MersenneTwister.cs](../MersenneTwister.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/CatSystem/ArcINT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
