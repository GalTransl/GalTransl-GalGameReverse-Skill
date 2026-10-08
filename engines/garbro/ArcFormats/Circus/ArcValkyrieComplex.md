# Circus / ArcValkyrieComplex：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAC/VC` / `GameRes.Formats.Circus.VcPacOpener` | `pac` | `01000000` | `False` |
| `PAK/VC` / `GameRes.Formats.Circus.VcPakOpener` | `pak` | `82758262` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `VcPakOpener.TryOpen` | `var signature = file.View.ReadBytes (0, 10);` |
| `VcPakOpener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (0x18) ^ ukey);` |
| `VcPakOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0x1C) ^ ukey;` |
| `VcPakOpener.TryOpen` | `var index = file.View.ReadBytes (0x20, index_size);` |
| `VcPakOpener.TryOpen` | `int name_length = LittleEndian.ToInt32 (index, index_pos);` |
| `VcPakOpener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, index_pos+4);` |
| `VcPakOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (index, index_pos+8);` |
| `VcPakOpener.OpenEntry` | `var data = vcarc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `VcPakOpener.UnpackCps` | `uint unpacked_size = (LittleEndian.ToUInt32 (input, 0) ^ 0xA415FCF) & 0xFFFFFFF;` |
| `ReverseBitStream.GetBits` | `int b = m_input.ReadByte();` |
| `VcPacOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `VcPacOpener.TryOpen` | `uint base_offset = file.View.ReadUInt32 (8);` |
| `VcPacOpener.TryOpen` | `uint file_size = file.View.ReadUInt32 (0xC);` |
| `VcPacOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x20);` |
| `VcPacOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset);` |
| `VcPacOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+4) + base_offset;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Circus.VcPakFile

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly byte Key ;
```

#### VcPakFile

```csharp
public VcPakFile (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, byte key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Circus.VcPakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] TrialSignature  = Encodings.cp932.GetBytes ("ＶＣ体験版") ;

static readonly byte[] RetailSignature = Encodings.cp932.GetBytes ("ＶＣ製品版") ;
```

#### VcPakOpener

```csharp
public VcPakOpener () {
    Extensions = new string[] { "pak" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var signature = file.View.ReadBytes (0, 10);
    bool is_trial = signature.SequenceEqual (TrialSignature);
    if (!is_trial && !signature.SequenceEqual (RetailSignature))
        return null;
    byte key = (byte)(is_trial ? 0x38 : 0x58);
    uint ukey = (uint)key << 8 | key;
    ukey |= ukey << 16;
    int count = (int)(file.View.ReadUInt32 (0x18) ^ ukey);
    if (!IsSaneCount (count))
        return null;
    uint index_size = file.View.ReadUInt32 (0x1C) ^ ukey;
    if (index_size >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (0x20, index_size);
    for (int i = 0; i < index.Length; ++i)
        index[i] ^= key;

    int index_pos = 4;
    int names_pos = count * 0x10;
    var dir = new List<Entry> (count);
    for (uint i = 0; i < count; ++i)
    {
        int name_length = LittleEndian.ToInt32 (index, index_pos);
        var name = Encodings.cp932.GetString (index, names_pos, name_length);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = LittleEndian.ToUInt32 (index, index_pos+4);
        entry.Size   = LittleEndian.ToUInt32 (index, index_pos+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        if (name.HasExtension (".cps"))
            entry.Type = "image";
        dir.Add (entry);
        index_pos += 0x10;
        names_pos += name_length + 1;
    }
    return new VcPakFile (file, this, dir, (byte)(is_trial ? 0x25 : 0x24));
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var vcarc = arc as VcPakFile;
    if (null == vcarc)
        return base.OpenEntry (arc, entry);
    var data = vcarc.File.View.ReadBytes (entry.Offset, entry.Size);
    for (int i = 0; i < data.Length; ++i)
        data[i] ^= vcarc.Key;
    if (entry.Name.HasExtension (".cs"))
    {
        for (int i = 0; i < data.Length; ++i)
            --data[i];
    }
    else if (entry.Name.HasExtension (".cps"))
    {
        data = UnpackCps (data);
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### UnpackCps

```csharp
byte[] UnpackCps (byte[] input) {
    uint unpacked_size = (LittleEndian.ToUInt32 (input, 0) ^ 0xA415FCF) & 0xFFFFFFF;
    int type = input[3] >> 4;
    if (type > 3)
        return input;
    DecryptCps (input);
    var output = new byte[unpacked_size];
    switch (type)
    {
    case 0: Buffer.BlockCopy (input, 4, output, 0, output.Length); break;
    case 1: UnpackV1 (input, output); break;
    case 2: UnpackV2 (input, output); break;
    case 3: UnpackV3 (input, output); break;
    }
    return output;
}
```

#### DecryptCps

```csharp
static void DecryptCps (byte[] input) {
    int length = input.Length;
    if (length < 0x308)
        return;

    input[4] ^= input[length - 1];
    byte key = 0xFF;

    length -= 8;
    int a = 8 + length - key;
    int b = 8 + length / 0x200 + key;
    byte t = input[a];
    input[a] = input[b];
    input[b] = t;

    a = 8 + key + 2 * (length / 0x200);
    b = 8 + length - 2 * key;
    t = input[a];
    input[a] = input[b];
    input[b] = t;
}
```

#### UnpackV1

```csharp
static void UnpackV1 (byte[] input, byte[] output) {
    int dst = 0;
    using (var mem = new MemoryStream (input, 4, input.Length-4))
    using (var bits = new ReverseBitStream (mem))
    {
        while (dst < output.Length)
        {
            int count = bits.GetBits (4);
            if (0 != bits.GetNextBit())
            {
                for (int i = 0; i <= count; ++i)
                    output[dst++] = (byte)bits.GetBits (8);
            }
            else
            {
                byte b = (byte)bits.GetBits (8);
                for (int i = 0; i < count; ++i)
                    output[dst++] = b;
            }
        }
    }
}
```

#### UnpackV2

```csharp
static void UnpackV2 (byte[] input, byte[] output) {
    output[output.Length-1] = input[36];
    using (var mem = new MemoryStream (input, 38, input.Length-38))
    using (var bits = new ReverseBitStream (mem))
    {
        for (int dst = 0; dst < output.Length; dst += 2)
        {
            if (0 != bits.GetNextBit())
            {
                output[dst+1] = (byte)bits.GetBits (8);
                output[dst]   = (byte)bits.GetBits (8);
            }
            else
            {
                int j;
                for (j = 0; j < 30; j += 2)
                {
                    if (0 != bits.GetNextBit())
                        break;
                }
                output[dst]   = input[4 + j];
                output[dst+1] = input[5 + j];
            }
        }
    }
}
```

#### UnpackV3

```csharp
static void UnpackV3 (byte[] input, byte[] output) {
    int src = 4;
    int dst = 0;
    if (output.Length <= 128)
    {
        Buffer.BlockCopy (input, src, output, dst, output.Length);
        return;
    }
    Buffer.BlockCopy (input, src, output, dst, 128);
    src += 128;
    dst += 128;
    using (var mem = new MemoryStream (input, src, input.Length-src))
    using (var bits = new ReverseBitStream (mem))
    {
        while (dst < output.Length)
        {
            if (0 != bits.GetNextBit())
            {
                int offset = bits.GetBits (7) + 1;
                int count  = bits.GetBits (4) + 2;
                Binary.CopyOverlapped (output, dst - offset, dst, count);
                dst += count;
            }
            else
            {
                output[dst++] = (byte)bits.GetBits (8);
            }
        }
    }
}
```

### GameRes.Formats.Circus.ReverseBitStream

继承/接口：`BitStream`, `IBitStream`。

#### GetBits

```csharp
public int GetBits (int count) {
    while (m_cached_bits < count)
    {
        int b = m_input.ReadByte();
        if (-1 == b)
            return -1;
        m_bits |= b << m_cached_bits;
        m_cached_bits += 8;
    }
    int value = 0;
    m_cached_bits -= count;
    while (count --> 0)
    {
        value |= (m_bits & 1) << count;
        m_bits >>= 1;
    }
    return value;
}
```

#### GetNextBit

```csharp
public int GetNextBit () {
    return GetBits (1);
}
```

### GameRes.Formats.Circus.VcPacOpener

继承/接口：`ArchiveFormat`。

#### VcPacOpener

```csharp
public VcPacOpener () {
    Extensions = new string[] { "pac" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    uint base_offset = file.View.ReadUInt32 (8);
    uint file_size = file.View.ReadUInt32 (0xC);
    if (base_offset >= file.MaxOffset || file_size != file.MaxOffset)
        return null;

    uint index_offset = 0x20;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x20);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        index_offset += 0x20;
        entry.Size   = file.View.ReadUInt32 (index_offset);
        entry.Offset = file.View.ReadUInt32 (index_offset+4) + base_offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index_offset += 0x18;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Circus/ArcValkyrieComplex.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
