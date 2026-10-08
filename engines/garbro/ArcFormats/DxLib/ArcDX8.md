# DxLib / ArcDX8：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DXA8` / `GameRes.Formats.DxLib.Dx8Opener` | `dxa`, `hud`, `usi`, `med`, `dat`, `bin`, `bcx`, `wolf` | `44580800` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Dx8Opener.TryOpen` | `IndexSize  = file.View.ReadUInt32 (4),` |
| `Dx8Opener.TryOpen` | `BaseOffset = file.View.ReadInt64 (8),` |
| `Dx8Opener.TryOpen` | `IndexOffset = file.View.ReadInt64 (0x10),` |
| `Dx8Opener.TryOpen` | `FileTable  = file.View.ReadInt64 (0x18),` |
| `Dx8Opener.TryOpen` | `DirTable   = file.View.ReadInt64 (0x20),` |
| `Dx8Opener.TryOpen` | `CodePage   = file.View.ReadInt32 (0x28),` |
| `Dx8Opener.TryOpen` | `Flags      = (DXA8Flags)file.View.ReadUInt32(0x2C),` |
| `Dx8Opener.TryOpen` | `HuffmanKB = file.View.ReadByte(0x30)` |
| `Dx8Opener.TryOpen` | `var headerBuffer = file.View.ReadBytes(dx.IndexOffset, (uint)(file.MaxOffset-dx.IndexOffset));` |
| `IndexReaderV8.ReadDirEntry` | `DirOffset = m_input.ReadInt64(),` |
| `IndexReaderV8.ReadDirEntry` | `ParentDirOffset = m_input.ReadInt64(),` |
| `IndexReaderV8.ReadDirEntry` | `FileCount = (int)m_input.ReadInt64(),` |
| `IndexReaderV8.ReadDirEntry` | `FileTable = m_input.ReadInt64()` |
| `IndexReaderV8.ReadFileTable` | `root = Path.Combine(root, ExtractFileName(m_input.ReadInt64()));` |
| `IndexReaderV8.ReadFileTable` | `var name_offset = m_input.ReadInt64();` |
| `IndexReaderV8.ReadFileTable` | `uint attr = (uint)m_input.ReadInt64();` |
| `IndexReaderV8.ReadFileTable` | `var offset = m_input.ReadInt64();` |
| `IndexReaderV8.ReadFileTable` | `var size = m_input.ReadInt64();` |
| `IndexReaderV8.ReadFileTable` | `var packed_size = m_input.ReadInt64();` |
| `IndexReaderV8.ReadFileTable` | `var huffman_packed_size = m_input.ReadInt64();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### 枚举值

```csharp
enum DXA8Flags : UInt32
        {
            DXA_FLAG_NO_KEY=1,
            DXA_FLAG_NO_HEAD_PRESS=1<<1,
        }
```

### GameRes.Formats.DxLib.DXA8PackedEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public bool HuffmanCompressed { get; set; }

public uint HuffmanSize { get; set; }

public uint LZSize { get; set; }
```

### GameRes.Formats.DxLib.DxArchive8

继承/接口：`DxArchive`。

#### 状态与常量

```csharp
public byte huffmanMaxKB ;
```

#### DxArchive8

```csharp
public DxArchive8(ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IDxKey enc, int version,byte huffmanKB) : base(arc, impl, dir, enc, version) {
    huffmanMaxKB = huffmanKB;
}
```

### GameRes.Formats.DxLib.DxHeaderV8

继承/接口：`DxHeader`。

#### 状态与常量

```csharp
public DXA8Flags Flags ;

public byte HuffmanKB ;
```

### GameRes.Formats.DxLib.Dx8Opener

继承/接口：`DxOpener`。

#### 状态与常量

```csharp
Dx8Scheme DefaultScheme = new Dx8Scheme { KnownKeys = new Dictionary<string, IDxKey>() }

internal enum DXA8Flags : UInt32 {
    DXA_FLAG_NO_KEY=1,
    DXA_FLAG_NO_HEAD_PRESS=1<<1,
}
```

#### Dx8Opener

```csharp
public Dx8Opener () {
    Extensions = new string[] { "dxa", "hud", "usi", "med", "dat", "bin", "bcx", "wolf" };
    Signatures = new[] { 0x00085844u };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var dx = new DxHeaderV8 {
        IndexSize  = file.View.ReadUInt32 (4),
        BaseOffset = file.View.ReadInt64 (8),
        IndexOffset = file.View.ReadInt64 (0x10),
        FileTable  = file.View.ReadInt64 (0x18),
        DirTable   = file.View.ReadInt64 (0x20),
        CodePage   = file.View.ReadInt32 (0x28),
        Flags      = (DXA8Flags)file.View.ReadUInt32(0x2C),
        HuffmanKB = file.View.ReadByte(0x30)
    };
    if (dx.DirTable >= dx.IndexSize || dx.FileTable >= dx.IndexSize)
        return null;
    IDxKey key = null;

    var headerBuffer = file.View.ReadBytes(dx.IndexOffset, (uint)(file.MaxOffset-dx.IndexOffset));
    bool isencrypted = (dx.Flags & DXA8Flags.DXA_FLAG_NO_KEY) == 0;

    if (isencrypted)
    {
        var keyStr = Query<DXAOpts>(arcStrings.ZIPEncryptedNotice).Keyword;
        key = new DxKey8(keyStr,dx.CodePage);

    }

    Decrypt(headerBuffer, 0, headerBuffer.Length, 0, key.Key);

    if ((dx.Flags & DXA8Flags.DXA_FLAG_NO_HEAD_PRESS) == 0)
    {
        byte[] huffmanBuffer = new byte[headerBuffer.Length];
        byte[] lzBuffer;
        headerBuffer.CopyTo(huffmanBuffer, 0);

        HuffmanDecoder decoder = new HuffmanDecoder(huffmanBuffer, (ulong)huffmanBuffer.LongLength);
        lzBuffer = decoder.Unpack();
        MemoryStream lzStream = new MemoryStream(lzBuffer);
        headerBuffer = Unpack(lzStream);

    }

    List<Entry> entries;

    using (var reader = IndexReader.Create(dx, 8, new MemoryStream(headerBuffer)))
    {
        entries = reader.Read();
    }
    return new DxArchive8(file, this,entries ,key, 8,dx.HuffmanKB);

}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    Stream input = arc.File.CreateStream(entry.Offset, entry.Size);
    var dx_arc = arc as DxArchive8;
    if (null == dx_arc)
        return input;
    var dx_ent = (DXA8PackedEntry)entry;
    long dec_offset =  dx_ent.UnpackedSize;
    var key = dx_arc.Encryption.GetEntryKey(dx_ent.Name);
    input = new EncryptedStream(input, dec_offset, key);

    byte[] tmpBuffer = new byte[dx_ent.Size];
    input.Read(tmpBuffer, 0, tmpBuffer.Length);
    if (dx_ent.HuffmanCompressed)
    {
        byte[] buffer = new byte[dx_ent.HuffmanSize];
        byte[] outBuffer = new byte[dx_ent.IsPacked ? dx_ent.LZSize : dx_ent.UnpackedSize];
        Array.Copy(tmpBuffer, buffer, dx_ent.HuffmanSize);
        HuffmanDecoder decoder = new HuffmanDecoder(buffer,dx_ent.HuffmanSize);
        byte[] partTmpBuffer = decoder.Unpack();

        var outBufSize = dx_ent.IsPacked ? dx_ent.LZSize : dx_ent.UnpackedSize;
        if(dx_arc.huffmanMaxKB != 0xff && outBufSize > dx_arc.huffmanMaxKB * 1024 * 2)
        {

            Array.Copy(partTmpBuffer,0, outBuffer, 0,dx_arc.huffmanMaxKB*1024);
            Array.Copy(partTmpBuffer,dx_arc.huffmanMaxKB*1024,outBuffer,outBuffer.Length-dx_arc.huffmanMaxKB*1024,dx_arc.huffmanMaxKB*1024);

            Array.Copy(tmpBuffer, dx_ent.HuffmanSize, outBuffer, dx_arc.huffmanMaxKB * 1024, outBufSize - dx_arc.huffmanMaxKB * 1024 * 2);
            tmpBuffer = outBuffer;
        } else
        {

            tmpBuffer = partTmpBuffer;
        }
    }
    if(dx_ent.IsPacked)
    {
        byte[] buffer = new byte[dx_ent.LZSize];
        tmpBuffer.CopyTo(buffer, 0);
        var tmpMemStream = new MemoryStream(buffer);
        tmpBuffer = Unpack(tmpMemStream);

    }
    return new BinMemoryStream(tmpBuffer, entry.Name);

}
```

### GameRes.Formats.DxLib.Dx8Opener.DXAOpts

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public byte[] Keyword ;
```

### GameRes.Formats.DxLib.IndexReaderV8

继承/接口：`IndexReader`。

#### 状态与常量

```csharp
readonly int m_entry_size ;
```

#### IndexReaderV8

```csharp
public IndexReaderV8(DxHeader header, int version, Stream input) : base(header, version, input) {
    m_entry_size = 0x48;
}
```

#### ReadDirEntry

```csharp
DxDirectory ReadDirEntry() {
    var dir = new DxDirectory
    {
        DirOffset = m_input.ReadInt64(),
        ParentDirOffset = m_input.ReadInt64(),
        FileCount = (int)m_input.ReadInt64(),
        FileTable = m_input.ReadInt64()
    };
    return dir;
}
```

#### ReadFileTable

```csharp
protected override void ReadFileTable(string root, long table_offset) {
    m_input.Position = m_header.DirTable + table_offset;
    var dir = ReadDirEntry();
    if (dir.DirOffset != -1 && dir.ParentDirOffset != -1)
    {
        m_input.Position = m_header.FileTable + dir.DirOffset;
        root = Path.Combine(root, ExtractFileName(m_input.ReadInt64()));
    }
    long current_pos = m_header.FileTable + dir.FileTable;
    for (int i = 0; i < dir.FileCount; ++i)
    {
        m_input.Position = current_pos;
        var name_offset = m_input.ReadInt64();
        uint attr = (uint)m_input.ReadInt64();
        m_input.Seek(0x18, SeekOrigin.Current);
        var offset = m_input.ReadInt64();
        if (0 != (attr & 0x10))
        {
            if (0 == offset || table_offset == offset)
                throw new InvalidFormatException("Infinite recursion in DXA directory index");
            ReadFileTable(root, offset);
        }
        else
        {
            var size = m_input.ReadInt64();
            var packed_size = m_input.ReadInt64();
            var huffman_packed_size = m_input.ReadInt64();
            var entry = FormatCatalog.Instance.Create<DXA8PackedEntry>(Path.Combine(root, ExtractFileName(name_offset)));
            entry.Offset = m_header.BaseOffset + offset;
            entry.UnpackedSize = (uint)size;
            entry.IsPacked = -1 != packed_size;
            entry.HuffmanCompressed = -1 != huffman_packed_size;
            entry.HuffmanSize = (uint)huffman_packed_size;
            entry.LZSize = (uint)packed_size;

            if (entry.HuffmanCompressed)
            {
                var outBufSize = entry.IsPacked ? packed_size : size;
                var dx8_hdr = (DxHeaderV8)m_header;
                if (outBufSize > dx8_hdr.HuffmanKB * 1024 * 2)
                {
                    huffman_packed_size += outBufSize - dx8_hdr.HuffmanKB * 1024 * 2;
                }
            }
            if (entry.IsPacked||entry.HuffmanCompressed)
                entry.Size = (uint)(huffman_packed_size!=-1 ? huffman_packed_size:packed_size);
            else
                entry.Size = (uint)size;
            m_dir.Add(entry);
        }
        current_pos += m_entry_size;
    }
}
```

### GameRes.Formats.DxLib.IndexReaderV8.DxDirectory

#### 状态与常量

```csharp
public long DirOffset ;

public long ParentDirOffset ;

public int FileCount ;

public long FileTable ;
```

## 配套算法与外部条件

- [ArcFormats/DxLib/ArcDX.cs](ArcDX.md)：本页引用的随包算法资料。
- [ArcFormats/DxLib/DxKey.cs](DxKey.md)：本页引用的随包算法资料。
- [ArcFormats/DxLib/HuffmanDecoder.cs](HuffmanDecoder.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/DxLib/ArcDX8.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
