# MokoPro / CompressedFile：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/NNNN` / `GameRes.Formats.Mokopro.NNNNOpener` | `dat` | `4e4e4e4e` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MokoCrypt.MokoCrypt` | `if (8 != stream.Read (header, 0, 8) \|\| !Binary.AsciiEqual (header, 0, "NNNN"))` |
| `MokoCrypt.MokoCrypt` | `m_unpacked_size = LittleEndian.ToInt32 (header, 4);` |
| `NNNNOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Mokopro.MokoCrypt

#### 状态与常量

```csharp
static readonly byte[] DefaultKey = new byte[] { 1, 0x23 }

byte[]  m_input ;

int     m_unpacked_size ;
```

#### MokoCrypt

```csharp
public MokoCrypt (Stream stream) {
    var header = new byte[8];
    if (8 != stream.Read (header, 0, 8) || !Binary.AsciiEqual (header, 0, "NNNN"))
        throw new InvalidFormatException();
    m_unpacked_size = LittleEndian.ToInt32 (header, 4);
    if (m_unpacked_size <= 0)
        throw new InvalidFormatException();
    m_input = new byte[stream.Length-8];
    stream.Read (m_input, 0, m_input.Length);
    Decrypt (m_input, DefaultKey);
}
```

#### UnpackStream

```csharp
public Stream UnpackStream () {
    var lzss = new LzssStream (new MemoryStream (m_input));
    lzss.Config.FrameFill = 0x20;
    return lzss;
}
```

#### UnpackBytes

```csharp
public byte[] UnpackBytes () {
    using (var mem = new MemoryStream (m_input))
    using (var lzss = new LzssReader (mem, m_input.Length, m_unpacked_size))
    {
        lzss.FrameFill = 0x20;
        lzss.Unpack();
        return lzss.Data;
    }
}
```

#### Decrypt

```csharp
public static void Decrypt (byte[] input, byte[] key) {
    for (int i = input.Length-2; i >= 0; --i)
    {
        input[i]   ^= (byte)(key[1] ^ input[i+1]);
        input[i+1] ^= (byte)(key[0] ^ input[i]);
    }
}
```

### GameRes.Formats.Mokopro.NNNNOpener

继承/接口：`ArchiveFormat`。

#### NNNNOpener

```csharp
public NNNNOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var name = Path.GetFileName (file.Name);
    var dir = new List<Entry> (1);
    var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
    entry.Offset = 0;
    entry.Size = (uint)file.MaxOffset;
    entry.UnpackedSize = file.View.ReadUInt32 (4);
    dir.Add (entry);
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var moko = new MokoCrypt (input);
    return moko.UnpackStream();
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/MokoPro/CompressedFile.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
