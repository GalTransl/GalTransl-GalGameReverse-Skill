# Illusion / ArcPP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PP/ILLUSION` / `GameRes.Formats.Illusion.PpOpener` | `pp` | `5b505056` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PpOpener.TryOpen` | `if (file.View.AsciiEqual (0, "[PPVER]\0"))` |
| `PpOpener.TryOpen` | `var version = file.View.ReadBytes (8, 4);` |
| `PpOpener.TryOpen` | `if (version.ToInt32 (0) < 0x6C)` |
| `PpOpener.TryOpen` | `var buffer = file.View.ReadBytes (base_offset, 5);` |
| `PpOpener.TryOpen` | `int count = buffer.ToInt32 (1);` |
| `PpOpener.TryOpen` | `var index = file.View.ReadBytes (index_offset, index_size);` |
| `PpOpener.TryOpen` | `entry.Size   = index.ToUInt32 (pos);` |
| `PpOpener.TryOpen` | `entry.Offset = index.ToUInt32 (pos+4);` |
| `PpOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Illusion.PpEncryptionScheme

#### 状态与常量

```csharp
public byte     Method ;

public uint[]   Key ;
```

### GameRes.Formats.Illusion.PpArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte Method ;
```

#### PpArchive

```csharp
public PpArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte encMethod, PpEncryptionScheme scheme)
    : base (arc, impl, dir) {
    Method = encMethod;
    Scheme = scheme;
}
```

### GameRes.Formats.Illusion.PpOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[][] DefaultIndexKey = new byte[][] {
    new byte[] { 0xFA, 0x49, 0x7B, 0x1C, 0xF9, 0x4D, 0x83, 0x0A },
    new byte[] { 0x3A, 0xE3, 0x87, 0xC2, 0xBD, 0x1E, 0xA6, 0xFE }
}

PpScheme DefaultScheme = new PpScheme {
    KnownKeys = new Dictionary<string, PpEncryptionScheme>()
}
```

#### PpOpener

```csharp
public PpOpener () {
    Signatures = new uint[] { 0x5650505B, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint base_offset = 0;
    int extra_size = 0;
    if (file.View.AsciiEqual (0, "[PPVER]\0"))
    {
        var version = file.View.ReadBytes (8, 4);
        DecryptIndex (version, 0, 4);
        if (version.ToInt32 (0) < 0x6C)
            return null;
        base_offset = 0xC;
        extra_size = 0x14;
    }

    var buffer = file.View.ReadBytes (base_offset, 5);

    DecryptIndex (buffer, 0, 1);
    byte encryption_method = buffer[0];
    if (encryption_method > 4)
        return null;

    DecryptIndex (buffer, 1, 4);
    int count = buffer.ToInt32 (1);
    if (!IsSaneCount (count))
        return null;

    var dir = new List<Entry> (count);
    uint index_offset = base_offset + 5;
    uint index_size = (uint)(count * (0x10C + extra_size));
    var index = file.View.ReadBytes (index_offset, index_size);
    index_offset += index_size;
    DecryptIndex (index, 0, index.Length);
    int pos = 0;
    for (int i = 0; i < count; ++i)
    {
        var name = Binary.GetCString (index, pos, 0x104);
        pos += 0x104;
        var entry = Create<Entry> (name);
        entry.Size   = index.ToUInt32 (pos);
        entry.Offset = index.ToUInt32 (pos+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        pos += 8 + extra_size;
    }
    var scheme = QueryEncryptionScheme (file);
    if (null == scheme)
        return null;
    return new PpArchive (file, this, dir, encryption_method, scheme);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = arc as PpArchive;
    if (null == parc || 2 == parc.Method)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    if (1 == parc.Method)
        DecryptData1 (data, parc.Scheme);
    else if (3 == parc.Method)
        DecryptData3 (data, parc.Scheme);
    else if (4 == parc.Method)
        data = UnpackData (data);
    return new BinMemoryStream (data, entry.Name);
}
```

#### UnpackData

```csharp
byte[] UnpackData (byte[] input) {
    return input;
}
```

#### DecryptData1

```csharp
void DecryptData1 (byte[] data, PpEncryptionScheme scheme) {
    if (scheme.Method > 2 || scheme.Key.Length == 0)
        return;
    if (0 == scheme.Method)
    {
        for (int i = 0; i < data.Length; ++i)
        {
            data[i] ^= (byte)scheme.Key[i % scheme.Key.Length];
        }
        return;
    }
    unsafe
    {
        fixed (byte* data8 = data)
        {
            if (1 == scheme.Method)
            {
                ushort* data16 = (ushort*)data8;
                int size = data.Length / 2;
                for (int i = 0; i < size; ++i)
                {
                    data16[i] ^= (ushort)scheme.Key[i % scheme.Key.Length];
                }
            }
            else if (2 == scheme.Method)
            {
                uint* data32 = (uint*)data8;
                int size = data.Length / 4;
                for (int i = 0; i < size; ++i)
                {
                    data32[i] ^= scheme.Key[i % scheme.Key.Length];
                }
            }
        }
    }
}
```

#### DecryptData3

```csharp
void DecryptData3 (byte[] data, PpEncryptionScheme scheme) {
    if (scheme.Key.Length < 8)
        return;
    var key0 = new ushort[] { (ushort)scheme.Key[0], (ushort)scheme.Key[1], (ushort)scheme.Key[2], (ushort)scheme.Key[3] };
    var key1 = new ushort[] { (ushort)scheme.Key[4], (ushort)scheme.Key[5], (ushort)scheme.Key[6], (ushort)scheme.Key[7] };
    unsafe
    {
        fixed (byte* data8 = data)
        {
            ushort* data16 = (ushort*)data8;
            int size = data.Length / 2;
            for (int i = 0; i < size; ++i)
            {
                int k = i & 3;
                key0[k] += key1[k];
                data16[i] ^= key0[k];
            }
        }
    }
}
```

#### DecryptIndex

```csharp
internal void DecryptIndex (byte[] data, int pos, int length) {
    var key0 = DefaultIndexKey[0].Clone() as byte[];
    var key1 = DefaultIndexKey[1];
    for (int i = 0; i < length; ++i)
    {
        int k = i & 7;
        key0[k] += key1[k];
        data[pos+i] ^= key0[k];
    }
}
```

#### QueryEncryptionScheme

```csharp
PpEncryptionScheme QueryEncryptionScheme (ArcView file) {
    var title = FormatCatalog.Instance.LookupGame (file.Name);
    if (string.IsNullOrEmpty (title))
        title = FormatCatalog.Instance.LookupGame (file.Name, @"..\*.exe");
    if (string.IsNullOrEmpty (title))
    {
        var options = Query<PpOptions> (arcStrings.ArcEncryptedNotice);
        if (null == options)
            return null;
        title = options.Scheme;
    }
    PpEncryptionScheme key;
    if (!KnownKeys.TryGetValue (title, out key))
        return null;
    return key;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Illusion/ArcPP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
