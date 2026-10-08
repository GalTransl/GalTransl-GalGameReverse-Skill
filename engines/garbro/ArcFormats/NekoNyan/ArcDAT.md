# NekoNyan / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/NekoNyan` / `GameRes.Formats.NekoNyan.NekoNyanDATOpenerV1` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArchiveCryptoV10.Initialize` | `byte[] rawFileNamesData = new byte[BitConverter.ToInt32(rawEntryData, 12) - (1024 + rawEntryData.Length)];` |
| `ArchiveCryptoV11.Initialize` | `byte[] rawFileNamesData = new byte[BitConverter.ToInt32(rawEntryData, 12) - (1024 + rawEntryData.Length)];` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NekoNyan.NekoNyanDATArchiveV1

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly ArchiveCryptoBase Crypto ;
```

#### NekoNyanDATArchiveV1

```csharp
public NekoNyanDATArchiveV1(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, ArchiveCryptoBase crypto)
    :base (arc, impl, dir) {
    this.Crypto = crypto;
}
```

### GameRes.Formats.NekoNyan.NekoNyanDATEntryV1

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Key { get; set; }
```

#### CheckValidRange

```csharp
public bool CheckValidRange(long maxOffset) {
    return this.Offset <= maxOffset && this.Size <= maxOffset && this.Offset <= maxOffset - this.Size;
}
```

### GameRes.Formats.NekoNyan.NekoNyanDATOpenerV1

继承/接口：`ArchiveFormat`。

#### NekoNyanDATOpenerV1

```csharp
public NekoNyanDATOpenerV1() {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    ArchiveCryptoBase crypto = QueryTitle(file.Name);
    if (crypto is null)
    {
        return null;
    }
    if (!crypto.Load(file, out List<ArchiveCryptoBase.FileEntry> entries))
    {
        return null;
    }

    List<Entry> dir = new List<Entry>(entries.Count);
    foreach(ArchiveCryptoBase.FileEntry fe in entries)
    {
        NekoNyanDATEntryV1 nnde = Create<NekoNyanDATEntryV1>(fe.FileName);
        nnde.Offset = fe.Offset;
        nnde.Size = fe.Size;
        nnde.Key = fe.Key;

        if (!nnde.CheckValidRange(file.MaxOffset))
        {
            return null;
        }

        dir.Add(nnde);
    }

    return new NekoNyanDATArchiveV1(file, this, dir, crypto);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    Stream stream = base.OpenEntry(arc, entry);
    if(!(arc is NekoNyanDATArchiveV1 nnarc) || !(entry is NekoNyanDATEntryV1 e))
    {
        return stream;
    }

    byte[] data = new byte[stream.Length];
    stream.Read(data, 0, data.Length);

    nnarc.Crypto.DecryptData(data, e.Key);

    return new MemoryStream(data, false);
}
```

#### QueryTitle

```csharp
private static ArchiveCryptoBase QueryTitle(string path) {
    string dir = Path.GetDirectoryName(path);
    while (!string.IsNullOrEmpty(dir) && Directory.GetFiles(dir, "*.exe", SearchOption.TopDirectoryOnly).Length == 0)
    {
        dir = Path.GetDirectoryName(dir);
    }
    if (string.IsNullOrEmpty(dir))
    {
        return null;
    }

    string up = Path.Combine(dir, "UnityPlayer.dll");
    string uch32 = Path.Combine(dir, "UnityCrashHandler32.exe");
    string uch64 = Path.Combine(dir, "UnityCrashHandler64.exe");
    if (!File.Exists(up) || !(File.Exists(uch32) || File.Exists(uch64)))
    {
        return null;
    }

    return ArchiveCryptoBase.CreateFactory(dir);
}
```

### GameRes.Formats.NekoNyan.ArchiveCryptoBase

#### 状态与常量

```csharp
private static readonly Dictionary<string, ArchiveCryptoBase> smTitles = new Dictionary<string, ArchiveCryptoBase>() {
    { "Aokana.exe", new ArchiveCryptoV10() },
    { "AokanaEXTRA1.exe", new ArchiveCryptoV10() },
    { "Kinkoi.exe", new ArchiveCryptoV10() },
    { "AokanaEXTRA2.exe", new ArchiveCryptoV11() },
    { "Clover Days Plus.exe", new ArchiveCryptoV12()},
    { "KoiChoco.exe", new ArchiveCryptoV13() },
}
```

#### CreateFactory

```csharp
public static ArchiveCryptoBase CreateFactory(string root) {
    foreach(KeyValuePair<string, ArchiveCryptoBase> pair in ArchiveCryptoBase.smTitles)
    {
        string path = Path.Combine(root, pair.Key);
        if (File.Exists(path))
        {
            return pair.Value;
        }
    }
    return null;
}
```

#### Load

```csharp
public bool Load(ArcView file, out List<FileEntry> entries) {
    using (ArcViewStream stream = file.CreateStream())
    {
        return this.Initialize(stream, out entries);
    }
}
```

#### DecryptData

```csharp
public void DecryptData(byte[] data, uint key) {
    this.Decrypt(data, key);
}
```

#### Initialize

```csharp
protected abstract bool Initialize(Stream stream, out List<FileEntry> entries) ;
```

#### ParseFileEntry

```csharp
protected abstract List<FileEntry> ParseFileEntry(ReadOnlySpan<byte> rawEntryData, ReadOnlySpan<byte> rawFileNamesData, int fileCount) ;
```

#### KeyGenerator

```csharp
protected abstract void KeyGenerator(Span<byte> tablePtr, uint key) ;
```

#### Decrypt

```csharp
protected abstract void Decrypt(Span<byte> data, uint key) ;
```

### GameRes.Formats.NekoNyan.ArchiveCryptoBase.FileEntry

#### 状态与常量

```csharp
public string FileName ;

public uint Offset ;

public uint Size ;

public uint Key ;
```

### GameRes.Formats.NekoNyan.ArchiveCryptoV10

继承/接口：`ArchiveCryptoBase`。

#### Initialize

```csharp
protected override bool Initialize(Stream stream, out List<FileEntry> entries) {
    entries = null;

    byte[] rawPkgInfo = new byte[1024];
    if (stream.Read(rawPkgInfo, 0, rawPkgInfo.Length) != rawPkgInfo.Length)
    {
        return false;
    }

    int fileCount = 0;
    uint rawFileEntryKey = 0u;
    uint rawFileNamesKey = 0u;
    {
        Span<int> rawPkgInfoPack4 = MemoryMarshal.Cast<byte, int>(rawPkgInfo);
        for (int i = 4; i < 255; ++i)
        {
            fileCount += rawPkgInfoPack4[i];
        }
        rawFileEntryKey = (uint)rawPkgInfoPack4[53];
        rawFileNamesKey = (uint)rawPkgInfoPack4[23];
    }

    byte[] rawEntryData = new byte[16 * fileCount];
    if (stream.Read(rawEntryData, 0, rawEntryData.Length) != rawEntryData.Length)
    {
        return false;
    }
    this.Decrypt(rawEntryData, rawFileEntryKey);

    byte[] rawFileNamesData = new byte[BitConverter.ToInt32(rawEntryData, 12) - (1024 + rawEntryData.Length)];
    if (stream.Read(rawFileNamesData, 0, rawFileNamesData.Length) != rawFileNamesData.Length)
    {
        return false;
    }
    this.Decrypt(rawFileNamesData, rawFileNamesKey);

    entries = this.ParseFileEntry(rawEntryData, rawFileNamesData, fileCount);
    return true;
}
```

#### ParseFileEntry

```csharp
protected override List<FileEntry> ParseFileEntry(ReadOnlySpan<byte> rawEntryData, ReadOnlySpan<byte> rawFileNamesData, int fileCount) {
    List<FileEntry> entries = new List<FileEntry>(fileCount);

    ReadOnlySpan<uint> rawEntryDataPack4 = MemoryMarshal.Cast<byte, uint>(rawEntryData);
    for (int i = 0; i < fileCount; ++i)
    {
        int pos = 4 * i;
        FileEntry entry = new FileEntry()
        {
            Size = rawEntryDataPack4[pos + 0],
            Key = rawEntryDataPack4[pos + 2],
            Offset = rawEntryDataPack4[pos + 3]
        };

        int fileNameOffset = (int)rawEntryDataPack4[pos + 1];
        int fileNameLen = rawFileNamesData.Slice(fileNameOffset).IndexOf((byte)0x00);

        entry.FileName = Encoding.UTF8.GetString(rawFileNamesData.Slice(fileNameOffset, fileNameLen).ToArray()).ToLower();

        entries.Add(entry);
    }

    return entries;
}
```

#### KeyGenerator

```csharp
protected override void KeyGenerator(Span<byte> tablePtr, uint key) {
    uint k1 = key * 0x00001CDF + 0x0000A74C;
    uint k2 = k1 << 0x11 ^ k1;

    for (int i = 0; i < 256; ++i)
    {
        k1 = k1 - key + k2;
        k2 = k1 + 0x38;
        k1 *= k2 & 0xEF;
        tablePtr[i] = (byte)k1;
        k1 >>= 1;
    }
}
```

#### Decrypt

```csharp
protected override void Decrypt(Span<byte> data, uint key) {
    Span<byte> table = stackalloc byte[256];
    this.KeyGenerator(table, key);
    for (int i = 0; i < data.Length; ++i)
    {
        byte temp = data[i];
        temp ^= table[i % 253];
        temp += 0x03;
        temp += table[i % 89];
        temp ^= 0x99;
        data[i] = temp;
    }
}
```

### GameRes.Formats.NekoNyan.ArchiveCryptoV11

继承/接口：`ArchiveCryptoV10`。

#### Initialize

```csharp
protected override bool Initialize(Stream stream, out List<FileEntry> entries) {
    entries = null;

    byte[] rawPkgInfo = new byte[1024];
    if (stream.Read(rawPkgInfo, 0, rawPkgInfo.Length) != rawPkgInfo.Length)
    {
        return false;
    }

    int fileCount = 0;
    uint rawFileEntryKey = 0u;
    uint rawFileNamesKey = 0u;
    {
        Span<int> rawPkgInfoPack4 = MemoryMarshal.Cast<byte, int>(rawPkgInfo);
        for (int i = 3; i < 255; ++i)
        {
            fileCount += rawPkgInfoPack4[i];
        }
        rawFileEntryKey = (uint)rawPkgInfoPack4[53];
        rawFileNamesKey = (uint)rawPkgInfoPack4[23];
    }

    byte[] rawEntryData = new byte[16 * fileCount];
    if (stream.Read(rawEntryData, 0, rawEntryData.Length) != rawEntryData.Length)
    {
        return false;
    }
    this.Decrypt(rawEntryData, rawFileEntryKey);

    byte[] rawFileNamesData = new byte[BitConverter.ToInt32(rawEntryData, 12) - (1024 + rawEntryData.Length)];
    if (stream.Read(rawFileNamesData, 0, rawFileNamesData.Length) != rawFileNamesData.Length)
    {
        return false;
    }
    this.Decrypt(rawFileNamesData, rawFileNamesKey);

    entries = this.ParseFileEntry(rawEntryData, rawFileNamesData, fileCount);
    return true;
}
```

#### KeyGenerator

```csharp
protected override void KeyGenerator(Span<byte> tablePtr, uint key) {
    uint k1 = key * 0x0000131C + 0x0000A740;
    uint k2 = k1 << 0x07 ^ k1;

    for (int i = 0; i < 256; ++i)
    {
        k1 = k1 - key + k2;
        k2 = k1 + 0x9C;
        k1 *= k2 & 0xCE;
        tablePtr[i] = (byte)k1;
        k1 >>= 3;
    }
}
```

#### Decrypt

```csharp
protected override void Decrypt(Span<byte> data, uint key) {
    Span<byte> table = stackalloc byte[256];
    this.KeyGenerator(table, key);
    for (int i = 0; i < data.Length; ++i)
    {
        byte temp = data[i];
        temp ^= table[i % 179];
        temp += 0x03;
        temp += table[i % 89];
        temp ^= 0x77;
        data[i] = temp;
    }
}
```

### GameRes.Formats.NekoNyan.ArchiveCryptoV12

继承/接口：`ArchiveCryptoV10`。

#### Decrypt

```csharp
protected override void Decrypt(Span<byte> data, uint key) {
    Span<byte> table = stackalloc byte[256];
    this.KeyGenerator(table, key);
    for (int i = 0; i < data.Length; ++i)
    {
        byte temp = data[i];
        temp ^= table[i % 253];
        temp += table[i % 59];
        temp ^= 0x99;
        data[i] = temp;
    }
}
```

### GameRes.Formats.NekoNyan.ArchiveCryptoV13

继承/接口：`ArchiveCryptoV11`。

#### KeyGenerator

```csharp
protected override void KeyGenerator(Span<byte> tablePtr, uint key) {
    uint k1 = key * 0x00001704u + 0x0000A140u;
    uint k2 = k1 << 0x07 ^ k1;

    for (int i = 0; i < 256; ++i)
    {
        k1 = k1 - key + k2;
        k2 = k1 + 0x155u;
        k1 *= k2 & 0xDCu;
        tablePtr[i] = (byte)k1;
        k1 >>= 2;
    }
}
```

#### Decrypt

```csharp
protected override void Decrypt(Span<byte> data, uint key) {
    Span<byte> table = stackalloc byte[256];
    this.KeyGenerator(table, key);
    for (int i = 0; i < data.Length; ++i)
    {
        byte temp = data[i];
        temp ^= table[i % 235];
        temp += 0x1F;
        temp += table[i % 87];
        temp ^= 0xA5;
        data[i] = temp;
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/NekoNyan/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
