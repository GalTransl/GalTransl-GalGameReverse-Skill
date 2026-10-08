# YuukiNovel / ArcYuuki：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PackageFile2` / `GameRes.Formats.YuukiNovel.YuukiOpener` | `exe` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `YuukiOpener.TryOpen` | `if (0x5A4D != file.View.ReadUInt16 (0))` |
| `YuukiOpener.TryOpen` | `if (!file.View.AsciiEqual (base_offset, "\x0cPackageFile2"))` |
| `YuukiOpener.TryOpen` | `int count = file.View.ReadUInt16 (base_offset + 0xD);` |
| `YuukiOpener.TryOpen` | `uint name_length = file.View.ReadByte (index_offset);` |
| `YuukiOpener.TryOpen` | `var name = file.View.ReadString (index_offset + 1, name_length);` |
| `YuukiOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset) + data_offset;` |
| `YuukiOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (index_offset + 4);` |
| `YuukiOpener.OpenEntry` | `if (sign.AsciiEqual (1, "YuukiNovel WorkFile"))` |
| `YuukiSchemeV2.CreateStream` | `uint seed = input.ReadUInt32();` |
| `EncryptedStream.ReadByte` | `public override int ReadByte () {` |
| `EncryptedStream.ReadByte` | `int b = BaseStream.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.YuukiNovel.YuukiOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly IYuukiScheme[] KnownSchemes = { new YuukiSchemeV1(), new YuukiSchemeV2() }
```

#### YuukiOpener

```csharp
public YuukiOpener () {
    Extensions = new[] { "exe" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0x5A4D != file.View.ReadUInt16 (0))
        return null;
    var exe = new ExeFile (file);
    uint base_offset = (uint)exe.Overlay.Offset;
    if (!file.View.AsciiEqual (base_offset, "\x0cPackageFile2"))
        return null;

    int count = file.View.ReadUInt16 (base_offset + 0xD);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = base_offset + 0xF;
    uint data_offset = index_offset + (uint)count * 0x108;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; i++)
    {
        uint name_length = file.View.ReadByte (index_offset);
        var name = file.View.ReadString (index_offset + 1, name_length);
        if (string.IsNullOrEmpty (name))
            return null;
        var entry = Create<Entry> (name);
        index_offset += 0x100;
        entry.Offset = file.View.ReadUInt32 (index_offset) + data_offset;
        entry.Size = file.View.ReadUInt32 (index_offset + 4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (entry.Name != "autorun.yne")
        return input;
    foreach (var scheme in KnownSchemes)
    {
        using (var stream = scheme.CreateStream (input))
        {
            var sign = new byte[20];
            stream.Read (sign, 0, sign.Length);
            input.Position = 0;
            if (sign.AsciiEqual (1, "YuukiNovel WorkFile"))
                return scheme.CreateStream (input);
        }
    }
    return input;
}
```

### GameRes.Formats.YuukiNovel.YuukiSchemeV1

继承/接口：`IYuukiScheme`。

#### CreateStream

```csharp
public Stream CreateStream (ArcViewStream input) {
    var key = new byte[] { 0x1F, 0x53, 0x58, 0x60, 0x86, 0x27, 0x11, 0xD5, 0x8B, 0xCA, 0x00, 0x33, 0x54, 0xC1, 0x08, 0x01 };
    return new ByteStringEncryptedStream (input, key, true);
}
```

### GameRes.Formats.YuukiNovel.YuukiSchemeV2

继承/接口：`IYuukiScheme`。

#### CreateStream

```csharp
public Stream CreateStream (ArcViewStream input) {
    uint seed = input.ReadUInt32();
    return new EncryptedStream (input, seed, true);
}
```

### GameRes.Formats.YuukiNovel.EncryptedStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
uint m_seed ;
```

#### EncryptedStream

```csharp
public EncryptedStream (Stream input, uint seed, bool leave_open = false)
    : base (input, leave_open) {
    m_seed = seed;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int read = BaseStream.Read (buffer, offset, count);
    for (int i = 0; i < read; ++i)
    {
        buffer[offset+i] ^= Rand();
    }
    return read;
}
```

#### ReadByte

```csharp
public override int ReadByte () {
    int b = BaseStream.ReadByte();
    if (-1 != b)
        b ^= Rand();
    return b;
}
```

#### Rand

```csharp
byte Rand () {
    m_seed = m_seed * 0x6C078965 + 1;
    return (byte)(m_seed >> 0x18);
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/YuukiNovel/ArcYuuki.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
