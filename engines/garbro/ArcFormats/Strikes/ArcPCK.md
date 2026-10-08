# Strikes / ArcPCK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCK/AVG` / `GameRes.Formats.Strikes.PckOpener` | `pck` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PckOpener.TryOpen` | `int seed = Binary.BigEndian (file.View.ReadInt32 (file.MaxOffset - 104));` |
| `PckOpener.TryOpen` | `var header = file.View.ReadBytes (file.MaxOffset - 100, 100);` |
| `PckOpener.TryOpen` | `uint length = BigEndian.ToUInt32 (header, 24);` |
| `PckOpener.TryOpen` | `uint idx_pos = BigEndian.ToUInt32 (header, 28);` |
| `PckOpener.TryOpen` | `uint idx_size = Binary.BigEndian (file.View.ReadUInt32 (idx_pos));` |
| `PckOpener.TryOpen` | `input.ReadInt32();` |
| `PckOpener.TryOpen` | `int count = Binary.BigEndian (input.ReadInt32());` |
| `PckOpener.TryOpen` | `var name = input.ReadCString (0x28);` |
| `PckOpener.TryOpen` | `entry.Offset = Binary.BigEndian (input.ReadUInt32());` |
| `PckOpener.TryOpen` | `entry.Size   = Binary.BigEndian (input.ReadUInt32());` |
| `PckOpener.TryOpen` | `entry.IsEncrypted = input.ReadInt32() != 0;` |
| `PckOpener.TryOpen` | `entry.UnpackedSize = input.ReadUInt32();` |
| `PckOpener.OpenEntry` | `uint test_size = Binary.BigEndian (arc.File.View.ReadUInt32 (pent.Offset + skip_size * 4));` |
| `PckOpener.OpenEntry` | `data = arc.File.View.ReadBytes (pent.Offset, pent.Size);` |
| `PckOpener.ReadChunk` | `var header = file.View.ReadUInt32 (offset);` |
| `PckOpener.ReadChunk` | `chunkSize = Binary.BigEndian (file.View.ReadUInt32 (offset + skipSize));` |
| `PckOpener.ReadChunk` | `var chunk = file.View.ReadBytes (offset + 4, size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Strikes.PckEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public bool IsEncrypted { get; set; }
```

### GameRes.Formats.Strikes.PckOpener

继承/接口：`ArchiveFormat`。

#### PckOpener

```csharp
public PckOpener () {
    ContainedFormats = new[] { "LAG", "BMP", "OGG", "WAV", "TXT" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!VFS.IsPathEqualsToFileName (file.Name, "AVGDatas.pck"))
        return null;
    int seed = Binary.BigEndian (file.View.ReadInt32 (file.MaxOffset - 104));
    var header = file.View.ReadBytes (file.MaxOffset - 100, 100);
    var rnd = new RandomGenerator();
    rnd.Init (seed);
    rnd.Decrypt (header, 0, header.Length);

    uint checksum = (uint)(header[1] | header[2] << 8 | header[0] << 16 | header[3] << 24) ^ 0xDEFD32D3;
    uint length = BigEndian.ToUInt32 (header, 24);
    if (checksum != length)
        return null;

    uint idx_pos = BigEndian.ToUInt32 (header, 28);
    uint idx_size = Binary.BigEndian (file.View.ReadUInt32 (idx_pos));

    uint index_size;
    var index = ReadChunk (file, 8, idx_pos + 4, out index_size);
    if (index_size >= 0x80000000)
    {
        index_size &= 0x7FFFFFFF;
        var unpacked = new byte[idx_size];
        LzssUnpack (index, index.Length, unpacked);
        index = unpacked;
    }
    using (var input = new BinMemoryStream (index))
    {
        var dir = new List<Entry>();
        int dir_count = 0;
        while (input.PeekByte() != -1)
        {
            input.ReadInt32();
            input.ReadInt32();
            input.ReadInt32();
            int count = Binary.BigEndian (input.ReadInt32());
            var dir_name = dir_count.ToString ("X4");
            for (int i = 0; i < count; ++i)
            {
                var name = input.ReadCString (0x28);
                name = Path.Combine (dir_name, name);
                var entry = Create<PckEntry> (name);
                entry.Offset = Binary.BigEndian (input.ReadUInt32());
                entry.Size   = Binary.BigEndian (input.ReadUInt32());
                entry.IsEncrypted = input.ReadInt32() != 0;
                entry.UnpackedSize = input.ReadUInt32();
                entry.IsPacked = entry.Size != entry.UnpackedSize;
                if (!entry.CheckPlacement (file.MaxOffset))
                    return null;
                dir.Add (entry);
            }
            ++dir_count;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PckEntry;
    if (null == pent || !(pent.IsEncrypted || pent.IsPacked))
        return base.OpenEntry (arc, entry);
    arc.File.View.Reserve (pent.Offset, pent.Size);
    int skip_size = 8;
    do
    {
        uint test_size = Binary.BigEndian (arc.File.View.ReadUInt32 (pent.Offset + skip_size * 4));
        if (test_size + 4 == pent.Size)
            break;
    }
    while (--skip_size > 0);
    byte[] data;
    uint data_size = pent.Size;
    if (0 == skip_size)
    {
        data = arc.File.View.ReadBytes (pent.Offset, pent.Size);
    }
    else
    {
        data = ReadChunk (arc.File, skip_size, pent.Offset, out data_size);
    }
    if (pent.IsEncrypted)
    {
        if (data_size >= 0x10)
            DecryptData (data, 0x10, 0xC53A9A6C);
        else
            DecryptData (data, data.Length, 0x6C9A3AC5);
    }
    Stream input = new BinMemoryStream (data, pent.Name);
    if (pent.IsPacked)
        input = new LzssStream (input);
    return input;
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, int length, uint key) {
    for (int i = 0; i < length; ++i)
    {
        data[i] ^= (byte)(key >> ((i & 3) << 3));
    }
}
```

#### ReadChunk

```csharp
byte[] ReadChunk (ArcView file, int skipSize, long offset, out uint chunkSize) {
    skipSize *= 4;
    var header = file.View.ReadUInt32 (offset);
    chunkSize = Binary.BigEndian (file.View.ReadUInt32 (offset + skipSize));
    uint size = chunkSize & 0x7FFFFFFF;
    var chunk = file.View.ReadBytes (offset + 4, size);
    if (skipSize > 0)
    {
        System.Buffer.BlockCopy (chunk, 0, chunk, 4, skipSize - 4);
        LittleEndian.Pack (header, chunk, 0);
    }
    return chunk;
}
```

#### LzssUnpack

```csharp
static internal int LzssUnpack (byte[] input, int in_length, byte[] output) {
    var frame = new byte[0x1000];
    int frame_pos = 0xFEE;
    int src = 0;
    int dst = 0;
    while (src < in_length)
    {
        int ctl = input[src++];
        for (int bit = 1; bit != 0x100; bit <<= 1)
        {
            if (0 != (ctl & bit))
            {
                if (src >= in_length)
                    return dst;
                byte b = input[src++];
                frame[frame_pos++ & 0xFFF] = b;
                output[dst++] = b;
            }
            else
            {
                if (src + 2 > in_length)
                    return dst;
                int lo = input[src++];
                int hi = input[src++];
                int offset = (hi & 0xF0) << 4 | lo;
                int count = Math.Min (3 + (hi & 0xF), output.Length - dst);
                while (count --> 0)
                {
                    byte b = frame[offset++ & 0xFFF];
                    frame[frame_pos++ & 0xFFF] = b;
                    output[dst++] = b;
                }
            }
        }
    }
    return dst;
}
```

### GameRes.Formats.Strikes.RandomGenerator

#### 状态与常量

```csharp
int         m_count ;

int[]       m_state = new int[56] ;
```

#### Init

```csharp
public void Init (int seed) {
    int n = 1;
    m_state[55] = seed;
    for (int i = 1; i <= 54; ++i)
    {
        int pos = 21 * i % 55;
        m_state[pos] = n;

        n = seed - n;
        if (n < 0)
            n += 1000000000;
        seed = m_state[pos];
    }
    Shuffle();
    Shuffle();
    Shuffle();
    m_count = 55;
}
```

#### Rand

```csharp
public uint Rand () {
    if (++m_count > 55)
    {
        Shuffle();
        m_count = 1;
    }
    return (uint)m_state[m_count];
}
```

#### Shuffle

```csharp
private void Shuffle () {
    for (int i = 1; i <= 24; ++i)
    {
        m_state[i] = m_state[i] - m_state[i+31];
        if (m_state[i] < 0)
            m_state[i] += 1000000000;
    }
    for (int i = 25; i <= 55; ++i)
    {
        m_state[i] = m_state[i] - m_state[i-24];
        if (m_state[i] < 0)
            m_state[i] += 1000000000;
    }
}
```

#### Decrypt

```csharp
public void Decrypt (byte[] input, int src, int length) {
    for (int i = src; i < length; i += 4)
    {
        uint key = Rand();
        input[i  ] ^= (byte)(key >> 24);
        input[i+1] ^= (byte)(key >> 16);
        input[i+2] ^= (byte)(key >> 8);
        input[i+3] ^= (byte)(key);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Strikes/ArcPCK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
