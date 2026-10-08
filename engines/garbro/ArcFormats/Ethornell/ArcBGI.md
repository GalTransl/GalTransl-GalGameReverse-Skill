# Ethornell / ArcBGI：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BURIKO` / `GameRes.Formats.BGI.Arc2Opener` | `arc` | `42555249` | `False` |
| `BGI` / `GameRes.Formats.BGI.ArcOpener` | `arc` | `5061636b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArcOpener.TryOpen` | `if (!file.View.AsciiEqual (4, "File    "))` |
| `ArcOpener.TryOpen` | `uint count = file.View.ReadUInt32 (12);` |
| `ArcOpener.TryOpen` | `string name = file.View.ReadString (index_offset, 0x10);` |
| `ArcOpener.TryOpen` | `entry.Offset = base_offset + file.View.ReadUInt32 (index_offset+0x10);` |
| `ArcOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x14);` |
| `ArcOpener.TryOpen` | `if (file.View.AsciiEqual (entry.Offset, "CompressedBG"))` |
| `ArcOpener.TryOpen` | `else if (file.View.AsciiEqual (entry.Offset+4, "bw  "))` |
| `ArcOpener.OpenEntry` | `if (pent.Size <= 0x220 \|\| !arc.File.View.AsciiEqual (entry_offset, "DSC FORMAT 1.00\0"))` |
| `ArcOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry_offset+0x14);` |
| `Arc2Opener.TryOpen` | `if (!file.View.AsciiEqual (4, "KO ARC20"))` |
| `Arc2Opener.Open` | `int count = file.View.ReadInt32 (12);` |
| `Arc2Opener.Open` | `string name = file.View.ReadString (index_offset, 0x60);` |
| `Arc2Opener.Open` | `var offset = base_offset + file.View.ReadUInt32 (index_offset+0x60);` |
| `Arc2Opener.Open` | `entry.Size = file.View.ReadUInt32 (index_offset+0x64);` |
| `Arc2Opener.Open` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `Arc2Opener.Open` | `else if (file.View.AsciiEqual (entry.Offset, "BSE 1."))` |
| `Arc2Opener.Open` | `else if (file.View.AsciiEqual (entry.Offset, "CompressedBG"))` |
| `Arc2Opener.Open` | `else if (file.View.AsciiEqual (entry.Offset+5, "w  "))` |
| `Arc2Opener.OpenEntry` | `if (entry.Size < 0x50 \|\| !arc.File.View.AsciiEqual (entry.Offset, "BSE 1."))` |
| `Arc2Opener.OpenEntry` | `int version = arc.File.View.ReadUInt16 (entry.Offset+8);` |
| `Arc2Opener.OpenEntry` | `ushort checksum = arc.File.View.ReadUInt16 (entry.Offset+0xA);` |
| `Arc2Opener.OpenEntry` | `uint key = arc.File.View.ReadUInt32 (entry.Offset+0xC);` |
| `Arc2Opener.OpenEntry` | `var header = arc.File.View.ReadBytes (entry.Offset+0x10, 0x40);` |
| `DscDecoder.DscDecoder` | `m_magic = (uint)input.ReadUInt16() << 16;` |
| `DscDecoder.DscDecoder` | `m_key = input.ReadUInt32();` |
| `DscDecoder.DscDecoder` | `int output_size = input.ReadInt32();` |
| `DscDecoder.DscDecoder` | `m_dec_count = input.ReadUInt32();` |
| `DscDecoder.Unpack` | `int src = Input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BGI.ArcOpener

继承/接口：`ArchiveFormat`。

#### ArcOpener

```csharp
public ArcOpener () {
    Extensions = new string[] { "arc" };
    ContainedFormats = new[] { "BGI", "CompressedBG", "BW", "SCR" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "File    "))
        return null;
    uint count = file.View.ReadUInt32 (12);
    if (count > 0xfffff)
        return null;
    uint index_size = 0x20 * count;
    if (index_size > file.View.Reserve (0x10, index_size))
        return null;
    var dir = new List<Entry> ((int)count);
    long index_offset = 0x10;
    long base_offset = index_offset + index_size;
    for (uint i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x10);
        var entry = Create<PackedEntry> (name);
        entry.Offset = base_offset + file.View.ReadUInt32 (index_offset+0x10);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x14);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x20;
    }
    foreach (var entry in dir.Where (e => string.IsNullOrEmpty (e.Type)))
    {
        if (file.View.AsciiEqual (entry.Offset, "CompressedBG"))
            entry.Type = "image";
        else if (file.View.AsciiEqual (entry.Offset+4, "bw  "))
            entry.Type = "audio";
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var entry_offset = entry.Offset;
    var input = arc.File.CreateStream (entry_offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null == pent)
        return input;
    if (!pent.IsPacked)
    {
        if (pent.Size <= 0x220 || !arc.File.View.AsciiEqual (entry_offset, "DSC FORMAT 1.00\0"))
            return input;
        pent.IsPacked = true;
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry_offset+0x14);
    }
    try
    {
        using (var decoder = new DscDecoder (input))
        {
            decoder.Unpack();
            return new BinMemoryStream (decoder.Output, entry.Name);
        }
    }
    catch (Exception X)
    {
        System.Diagnostics.Trace.WriteLine (X.Message, "BgiOpener");
        return arc.File.CreateStream (entry_offset, entry.Size);
    }
}
```

### GameRes.Formats.BGI.Arc2Opener

继承/接口：`ArcOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (4, "KO ARC20"))
        return null;
    return Open (file);
}
```

#### Open

```csharp
protected ArcFile Open (ArcView file) {
    int count = file.View.ReadInt32 (12);
    if (!IsSaneCount (count))
        return null;
    uint index_size = 0x80 * (uint)count;
    if (index_size > file.View.Reserve (0x10, index_size))
        return null;
    var dir = new List<Entry> (count);
    long index_offset = 0x10;
    long base_offset = index_offset + index_size;
    for (uint i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, 0x60);
        var offset = base_offset + file.View.ReadUInt32 (index_offset+0x60);
        var entry = new PackedEntry { Name = name, Offset = offset };
        entry.Size = file.View.ReadUInt32 (index_offset+0x64);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x80;
    }
    foreach (var entry in dir)
    {
        uint signature = file.View.ReadUInt32 (entry.Offset);
        var res = AutoEntry.DetectFileType (signature);
        if (res != null)
            entry.Type = res.Type;
        else if (file.View.AsciiEqual (entry.Offset, "BSE 1."))
            entry.Type = "image";
        else if (file.View.AsciiEqual (entry.Offset, "CompressedBG"))
            entry.Type = "image";
        else if (file.View.AsciiEqual (entry.Offset+5, "w  "))
            entry.Type = "audio";
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (entry.Size < 0x50 || !arc.File.View.AsciiEqual (entry.Offset, "BSE 1."))
        return base.OpenEntry (arc, entry);
    int version = arc.File.View.ReadUInt16 (entry.Offset+8);
    if (version != 0x100 && version != 0x101)
        return base.OpenEntry (arc, entry);

    ushort checksum = arc.File.View.ReadUInt16 (entry.Offset+0xA);
    uint key = arc.File.View.ReadUInt32 (entry.Offset+0xC);
    var header = arc.File.View.ReadBytes (entry.Offset+0x10, 0x40);
    if (0x101 == version)
        DecryptBse (header, new BseGenerator101 (key));
    else
        DecryptBse (header, new BseGenerator100 (key));
    var body = arc.File.CreateStream (entry.Offset+0x50, entry.Size-0x50);
    return new PrefixStream (header, body);
}
```

#### DecryptBse

```csharp
void DecryptBse (byte[] data, IBseGenerator decoder) {
    var decoded = new bool[0x40];
    for (int i = 0; i < decoded.Length; ++i)
    {
        int dst = decoder.NextKey() & 0x3F;
        while (decoded[dst])
        {
            dst = (dst + 1) & 0x3F;
        }
        int shift = decoder.NextKey() & 7;
        bool right_shift = (decoder.NextKey() & 1) == 0;
        byte symbol = (byte)(data[dst] - decoder.NextKey());
        if (right_shift)
        {
            data[dst] = Binary.RotByteR (symbol, shift);
        }
        else
        {
            data[dst] = Binary.RotByteL (symbol, shift);
        }
        decoded[dst] = true;
    }
}
```

### GameRes.Formats.BGI.BgiDecoderBase

继承/接口：`MsbBitStream`。

#### 状态与常量

```csharp
protected uint      m_key ;

protected uint      m_magic ;
```

#### UpdateKey

```csharp
protected byte UpdateKey () {
    uint v0 = 20021 * (m_key & 0xffff);
    uint v1 = m_magic | (m_key >> 16);
    v1 = v1 * 20021 + m_key * 346;
    v1 = (v1 + (v0 >> 16)) & 0xffff;
    m_key = (v1 << 16) + (v0 & 0xffff) + 1;
    return (byte)v1;
}
```

### GameRes.Formats.BGI.DscDecoder

继承/接口：`BgiDecoderBase`。

#### 状态与常量

```csharp
byte[]    m_output ;

uint      m_dec_count ;

public byte[] Output { get { return m_output; } }
```

#### DscDecoder

```csharp
public DscDecoder (IBinaryStream input) : base (input.AsStream) {
    m_magic = (uint)input.ReadUInt16() << 16;
    input.Position = 0x10;
    m_key = input.ReadUInt32();
    int output_size = input.ReadInt32();
    m_dec_count = input.ReadUInt32();
    m_output = new byte[output_size];
}
```

#### Unpack

```csharp
public void Unpack () {
    Input.Position = 0x20;
    HuffmanCode[] hcodes = new HuffmanCode[512];
    HuffmanNode[] hnodes = new HuffmanNode[1023];

    int leaf_node_count = 0;
    for (ushort i = 0; i < 512; i++)
    {
        int src = Input.ReadByte();
        if (-1 == src)
            throw new EndOfStreamException ("Incomplete compressed stream");
        byte depth = (byte)(src - UpdateKey());
        if (0 != depth)
        {
            hcodes[leaf_node_count].Depth = depth;
            hcodes[leaf_node_count].Code = i;
            leaf_node_count++;
        }
    }
    Array.Sort (hcodes, 0, leaf_node_count);
    CreateHuffmanTree (hnodes, hcodes, leaf_node_count);
    HuffmanDecompress (hnodes, m_dec_count);
}
```

#### CreateHuffmanTree

```csharp
static void CreateHuffmanTree (HuffmanNode[] hnodes, HuffmanCode[] hcode, int node_count) {
    var nodes_index = new int[2,512];
    int next_node_index = 1;
    int depth_nodes = 1;
    int depth = 0;
    int child_index = 0;
    nodes_index[0,0] = 0;
    for (int n = 0; n < node_count; )
    {
        int huffman_nodes_index = child_index;
        child_index ^= 1;

        int depth_existed_nodes = 0;
        while (n < hcode.Length && hcode[n].Depth == depth)
        {
            var node = new HuffmanNode { IsParent = false, Code = hcode[n++].Code };
            hnodes[nodes_index[huffman_nodes_index, depth_existed_nodes]] = node;
            depth_existed_nodes++;
        }
        int depth_nodes_to_create = depth_nodes - depth_existed_nodes;
        for (int i = 0; i < depth_nodes_to_create; i++)
        {
            var node = new HuffmanNode { IsParent = true };
            nodes_index[child_index, i * 2]     = node.LeftChildIndex = next_node_index++;
            nodes_index[child_index, i * 2 + 1] = node.RightChildIndex = next_node_index++;
            hnodes[nodes_index[huffman_nodes_index, depth_existed_nodes+i]] = node;
        }
        depth++;
        depth_nodes = depth_nodes_to_create * 2;
    }
}
```

#### HuffmanDecompress

```csharp
int HuffmanDecompress (HuffmanNode[] hnodes, uint dec_count) {
    int dst_ptr = 0;

    for (uint k = 0; k < dec_count; k++)
    {
        int node_index = 0;
        do
        {
            int bit = GetNextBit();
            if (-1 == bit)
                throw new EndOfStreamException();
            if (0 == bit)
                node_index = hnodes[node_index].LeftChildIndex;
            else
                node_index = hnodes[node_index].RightChildIndex;
        }
        while (hnodes[node_index].IsParent);

        int code = hnodes[node_index].Code;
        if (code >= 256)
        {
            int offset = GetBits (12);
            if (-1 == offset)
                break;
            int count = (code & 0xff) + 2;
            offset += 2;
            Binary.CopyOverlapped (m_output, dst_ptr - offset, dst_ptr, count);
            dst_ptr += count;
        } else
            m_output[dst_ptr++] = (byte)code;
    }
    return dst_ptr;
}
```

### GameRes.Formats.BGI.DscDecoder.HuffmanCode

继承/接口：`IComparable<HuffmanCode>`。

#### 状态与常量

```csharp
public ushort Code ;

public ushort Depth ;
```

#### CompareTo

```csharp
public int CompareTo (HuffmanCode other) {
    int cmp = (int)Depth - (int)other.Depth;
    if (0 == cmp)
        cmp = (int)Code - (int)other.Code;
    return cmp;
}
```

### GameRes.Formats.BGI.DscDecoder.HuffmanNode

#### 状态与常量

```csharp
public bool IsParent ;

public int  Code ;

public int  LeftChildIndex ;

public int  RightChildIndex ;
```

### GameRes.Formats.BGI.BseGenerator100

继承/接口：`IBseGenerator`。

#### 状态与常量

```csharp
int    m_key ;
```

#### BseGenerator100

```csharp
public BseGenerator100 (uint key) {
    m_key = (int)key;
}
```

#### NextKey

```csharp
public int NextKey () {
    uint v = (uint)(((m_key * 257 >> 8) + m_key * 97 + 23) ^ 0xA6CD9B75);
    m_key = (int)Binary.RotR (v, 16);
    return m_key;
}
```

### GameRes.Formats.BGI.BseGenerator101

继承/接口：`IBseGenerator`。

#### 状态与常量

```csharp
int    m_key ;
```

#### BseGenerator101

```csharp
public BseGenerator101 (uint key) {
    m_key = (int)key;
}
```

#### NextKey

```csharp
public int NextKey () {
    uint v = (uint)((m_key * 127 >> 7) + m_key * 83 + 53) ^ 0xB97A7E5C;
    m_key = (int)Binary.RotR (v, 16);
    return m_key;
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。
- [ArcFormats/Ethornell/ImageCBG.cs](ImageCBG.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Ethornell/ArcBGI.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
