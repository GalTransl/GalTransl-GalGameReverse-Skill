# Pias / EncryptedGraphDat：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/PIAS/ENC` / `GameRes.Formats.Pias.EncryptedDatOpener` | `dat` | `2ba6f302` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `EncryptedIndexReader.GetIndex` | `uint seed = m_arc.View.ReadUInt32 (entry.Offset);` |
| `EncryptedIndexReader.GetIndex` | `entry.Size = (buffer.ToUInt32 (0) & 0xFFFFFu) + 8u;` |
| `EncryptedIndexReader.GetIndex` | `uint seed = m_arc.View.ReadUInt32 (offset);` |
| `EncryptedIndexReader.GetIndex` | `uint entry_size = (buffer.ToUInt32 (0) & 0xFFFFFu) + 8u;` |
| `EncryptedDatOpener.OpenEncrypted` | `uint seed = arc.File.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Pias.PiasEncryptedArchive

继承/接口：`ArcFile`。

### GameRes.Formats.Pias.EncryptedIndexReader

继承/接口：`IndexReader`。

#### GetIndex

```csharp
new public List<Entry> GetIndex () {
    if (m_res > 0)
    {
        var text_name = VFS.ChangeFileName (m_arc.Name, "text.dat");
        if (!VFS.FileExists (text_name))
            return null;
        IBinaryStream input = VFS.OpenBinaryStream (text_name);
        try
        {
            if (!DatOpener.EncryptedSignatures.Contains (input.Signature))
                return null;

            input.Position = 4;
            var rnd = new KeyGenerator (1);
            rnd.Seed (input.Signature);
            var crypto = new InputCryptoStream (input.AsStream, new PiasTransform (rnd));
            input = new BinaryStream (crypto, text_name);

            var reader = new TextReader (input);
            m_dir = reader.GetResourceList ((int)m_res);
        }
        finally
        {
            input.Dispose();
        }
    }
    IsEncrypted = ResourceType.Graphics == m_res;
    if (null == m_dir)
    {
        m_dir = new List<Entry>();
    }
    if (!IsEncrypted)
    {
        if (!FillEntries())
            return null;
        return m_dir;
    }
    var buffer = new byte[4];
    var key = new KeyGenerator (0);
    for (int i = m_dir.Count - 1; i >= 0; --i)
    {
        var entry = m_dir[i];
        uint seed = m_arc.View.ReadUInt32 (entry.Offset);
        m_arc.View.Read (entry.Offset+4, buffer, 0, 4);
        key.Seed (seed);
        Decrypt (buffer, 0, 4, key);
        entry.Size = (buffer.ToUInt32 (0) & 0xFFFFFu) + 8u;
        entry.Name = GetName (entry.Offset, i);
        entry.Type = "image";
    }
    var known_offsets = new HashSet<long> (m_dir.Select (e => e.Offset));
    long offset = 0;
    while (offset < m_arc.MaxOffset)
    {
        uint seed = m_arc.View.ReadUInt32 (offset);
        m_arc.View.Read (offset+4, buffer, 0, 4);
        key.Seed (seed);
        Decrypt (buffer, 0, 4, key);
        uint entry_size = (buffer.ToUInt32 (0) & 0xFFFFFu) + 8u;
        if (!known_offsets.Contains (offset))
        {
            var entry = new Entry {
                Name = GetName (offset, m_dir.Count) + "_",
                Type = "image",
                Offset = offset,
                Size = entry_size,
            };
            if (!entry.CheckPlacement (m_arc.MaxOffset))
                return null;
            m_dir.Add (entry);
        }
        offset += entry_size + 4;
    }
    return m_dir;
}
```

#### Decrypt

```csharp
internal static void Decrypt (byte[] data, int pos, int length, KeyGenerator key) {
    for (int i = 0; i < length; ++i)
    {
        data[pos+i] ^= (byte)key.Next();
    }
}
```

### GameRes.Formats.Pias.EncryptedDatOpener

继承/接口：`DatOpener`。

#### EncryptedDatOpener

```csharp
public EncryptedDatOpener () {
    Signatures = new[] { 0x02F3A62Bu, 0u };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arc_name = Path.GetFileName (file.Name).ToLowerInvariant();

    ResourceType resource_type = ResourceType.Undefined;
    if ("sound.dat" == arc_name)
        resource_type = ResourceType.Sound;
    else if ("graph.dat" == arc_name)
        resource_type = ResourceType.Graphics;
    else
        return null;

    var index = new EncryptedIndexReader (file, resource_type);
    var dir = index.GetIndex();
    if (null == dir)
        return null;
    if (index.IsEncrypted)
        return new PiasEncryptedArchive (file, this, dir);
    else
        return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Type != "audio")
        return OpenEncrypted (arc, entry);
    var format = new WaveFormat
    {
        FormatTag = 1,
        Channels = 2,
        SamplesPerSecond = 22050,
        AverageBytesPerSecond = 88200,
        BitsPerSample = 16,
        BlockAlign = 4,
    };
    return OpenAudioEntry (arc, entry, format);
}
```

#### OpenEncrypted

```csharp
public Stream OpenEncrypted (ArcFile arc, Entry entry) {
    uint seed = arc.File.View.ReadUInt32 (entry.Offset);
    var stream = arc.File.CreateStream (entry.Offset+4, entry.Size);
    var key = new KeyGenerator (0);
    key.Seed (seed);
    return new InputCryptoStream (stream, new PiasTransform (key));
}
```

### GameRes.Formats.Pias.KeyGenerator

#### 状态与常量

```csharp
int     m_type ;

uint    m_seed ;
```

#### KeyGenerator

```csharp
public KeyGenerator (int type) {
    m_type = type;
    m_seed = 0;
}
```

#### Seed

```csharp
public void Seed (uint seed) {
    m_seed = seed;
}
```

#### Next

```csharp
public uint Next () {
    uint y, x;
    if (0 == m_type)
    {
        x = 0xD22;
        y = 0x849;
    }
    else if (1 == m_type)
    {
        x = 0xF43;
        y = 0x356B;
    }
    else if (2 == m_type)
    {
        x = 0x292;
        y = 0x57A7;
    }
    else
    {
        x = 0;
        y = 0;
    }
    uint a = x + m_seed * y;
    uint b = 0;
    if ((a & 0x400000) != 0)
        b = 1;
    if ((a & 0x400) != 0)
        b ^= 1;
    if ((a & 1) != 0)
        b ^= 1;
    m_seed = (a >> 1) | (b != 0 ? 0x80000000u : 0u);
    return m_seed;
}
```

### GameRes.Formats.Pias.PiasTransform

继承/接口：`ByteTransform`。

#### 状态与常量

```csharp
KeyGenerator     m_key ;
```

#### PiasTransform

```csharp
public PiasTransform (KeyGenerator key) {
    m_key = key;
}
```

#### TransformBlock

```csharp
public override int TransformBlock (byte[] inputBuffer, int inputOffset, int inputCount,
                           byte[] outputBuffer, int outputOffset) {
    for (int i = 0; i < inputCount; ++i)
    {
        outputBuffer[outputOffset++] = (byte)(m_key.Next() ^ inputBuffer[inputOffset+i]);
    }
    return inputCount;
}
```

## 配套算法与外部条件

- [ArcFormats/SimpleEncryption.cs](../../ArcFormats/SimpleEncryption.md)：本页引用的随包算法资料。
- [Legacy/Pias/ArcDAT.cs](ArcDAT.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Pias/EncryptedGraphDat.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
