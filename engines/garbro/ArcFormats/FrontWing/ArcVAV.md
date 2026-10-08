# FrontWing / ArcVAV：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/vav` / `GameRes.Formats.FrontWing.PakOpener` | `pak` | `76617600` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int version = file.View.ReadInt32 (4);` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `PakOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0xC);` |
| `PakOpener.TryOpen` | `var name = file.View.ReadString (index_offset, name_size);` |
| `PakOpener.TryOpen` | `entry.Size         = file.View.ReadUInt32 (index_offset);` |
| `PakOpener.TryOpen` | `entry.UnpackedSize = file.View.ReadUInt32 (index_offset+4);` |
| `PakOpener.TryOpen` | `entry.Offset       = file.View.ReadUInt32 (index_offset+8);` |
| `PakOpener.TryOpen` | `entry.Compression  = file.View.ReadInt32 (index_offset+0xC);` |
| `PakOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `PakOpener.BuildHuffmanTree` | `tree[i].Weight = input.ReadByte() ^ 0x55;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FrontWing.VavEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public int  Compression ;
```

### GameRes.Formats.FrontWing.VavArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public int  Version ;
```

#### VavArchive

```csharp
public VavArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version)
    : base (arc, impl, dir) {
    Version = version;
}
```

### GameRes.Formats.FrontWing.PakOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (4);
    if (version != 100 && version != 200 && version != 201)
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    bool is_voice = Path.GetFileNameWithoutExtension (file.Name).Equals ("voice", StringComparison.OrdinalIgnoreCase);
    uint index_offset = file.View.ReadUInt32 (0xC);
    uint name_size = version < 200 ? 0x10u : 0x20u;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, name_size);
        var entry = Create<VavEntry> (name);
        index_offset += name_size;
        entry.Size         = file.View.ReadUInt32 (index_offset);
        entry.UnpackedSize = file.View.ReadUInt32 (index_offset+4);
        entry.Offset       = file.View.ReadUInt32 (index_offset+8);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Compression  = file.View.ReadInt32 (index_offset+0xC);
        entry.IsPacked     = (entry.Compression & 0x90) != 0;
        if (is_voice)
            entry.Type = "audio";
        dir.Add (entry);
        index_offset += 0x18;
    }
    return new VavArchive (file, this, dir, version);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var vent = entry as VavEntry;
    if (null == vent)
        return base.OpenEntry (arc, entry);
    var varc = arc as VavArchive;
    bool old_version = varc != null && varc.Version < 200;
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    int data_length = data.Length;
    if ((vent.Compression & 0x80) != 0)
    {
        var output = new byte[vent.UnpackedSize];
        data_length = UnpackHuffman (data, data_length, output);
        data = output;
    }
    if ((vent.Compression & 0x10) != 0)
    {
        var output = new byte[vent.UnpackedSize];
        UnpackRle (data, data_length, output);
        data = output;
    }
    DecryptEntry (data, vent.Compression & 0xF, old_version);
    return new BinMemoryStream (data);
}
```

#### DecryptEntry

```csharp
void DecryptEntry (byte[] data, int start, bool old_version = false) {
    if (start > 0)
    {
        for (int i = start; i < data.Length; ++i)
            data[i] ^= data[i-start];
    }
    else
    {
        int data_length = old_version ? 1 : data.Length;
        for (int i = 0; i < data_length; ++i)
            data[i] ^= 0x55;
    }
}
```

#### UnpackRle

```csharp
int UnpackRle (byte[] input, int input_length, byte[] output) {
    int src = 0;
    int dst = 0;
    while (dst < output.Length)
    {
        byte rle = input[src++];
        int count = Math.Min (rle & 0x7F, output.Length - dst);
        if (0 != (rle & 0x80))
        {
            byte v = input[src++];
            while (count --> 0)
                output[dst++] = v;
        }
        else
        {
            Buffer.BlockCopy (input, src, output, dst, count);
            src += count;
            dst += count;
        }
    }
    return dst;
}
```

#### UnpackHuffman

```csharp
int UnpackHuffman (byte[] input, int input_length, byte[] output) {
    using (var mem = new MemoryStream (input, 0, input_length))
    {
        var tree = new HuffmanNode[0x201];
        ushort root = BuildHuffmanTree (tree, mem);
        using (var bits = new MsbBitStream (mem))
        {
            int dst = 0;
            for (;;)
            {
                ushort symbol = root;
                while (symbol > 0x100)
                {
                    int bit = bits.GetBits (1);
                    if (-1 == bit)
                        return dst;
                    if (bit != 0)
                        symbol = tree[symbol].RChild;
                    else
                        symbol = tree[symbol].LChild;
                }
                if (0x100 == symbol)
                    return dst;
                output[dst++] = (byte)symbol;
            }
        }
    }
}
```

#### BuildHuffmanTree

```csharp
ushort BuildHuffmanTree (HuffmanNode[] tree, Stream input) {
    for (int i = 0; i < 0x100; ++i)
    {
        tree[i].Weight = input.ReadByte() ^ 0x55;
    }
    ushort root = 0x100;
    tree[root].Weight = 1;
    ushort lhs = 0x200;
    ushort rhs = 0x200;
    for (;;)
    {
        int lmin = 0x10000;
        int rmin = 0x10000;
        for (ushort i = 0; i < 0x201; ++i)
        {
            int w = tree[i].Weight;
            if (w != 0 && w < rmin)
            {
                rmin = lmin;
                lmin = w;
                rhs = lhs;
                lhs = i;
            }
        }
        if (rmin == 0x10000 || lmin == 0x10000 || lmin == 0 || rmin == 0)
            break;
        ++root;
        tree[root].LChild = lhs;
        tree[root].RChild = rhs;
        tree[root].Weight = rmin + lmin;
        tree[lhs].Weight = 0;
        tree[rhs].Weight = 0;
    }
    return root;
}
```

### GameRes.Formats.FrontWing.PakOpener.HuffmanNode

#### 状态与常量

```csharp
public int      Weight ;

public ushort   LChild ;

public ushort   RChild ;
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/FrontWing/ArcVAV.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
