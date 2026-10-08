# KApp / ImageCGD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CgdMetaData.FromStream` | `int unpacked_size = file.ReadInt32();` |
| `CgdMetaData.FromStream` | `file.ReadInt32();` |
| `CgdMetaData.FromStream` | `byte compression = (byte)file.ReadUInt16();` |
| `CgdMetaData.FromStream` | `uint header_size = file.ReadUInt16();` |
| `CgdMetaData.FromStream` | `uint id = file.ReadUInt32();` |
| `CgdMetaData.FromStream` | `ushort width  = file.ReadUInt16();` |
| `CgdMetaData.FromStream` | `ushort height = file.ReadUInt16();` |
| `CgdMetaData.FromStream` | `ushort bpp    = file.ReadUInt16();` |
| `KTool.DecompressRle` | `sbyte ctl = input.ReadInt8();` |
| `KTool.DecompressRle` | `output[dst] = input.ReadUInt8();` |
| `KTool.DecompressRle` | `byte v = input.ReadUInt8();` |
| `KTool.DecompressRle` | `ctl = input.ReadInt8();` |
| `HuffmanDecoder.Unpack` | `bits = m_input.ReadByte();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KApp.CgdMetaData

继承/接口：`ImageMetaData`。

#### 状态与常量

```csharp
public uint DataOffset ;

public int  UnpackedSize ;

public byte Compression ;

public bool RgbOrder ;
```

#### FromStream

```csharp
internal static CgdMetaData FromStream (IBinaryStream file, uint offset) {
    file.Position = offset;
    int unpacked_size = file.ReadInt32();
    file.ReadInt32();
    byte compression = (byte)file.ReadUInt16();
    uint header_size = file.ReadUInt16();
    uint id = file.ReadUInt32();
    if (header_size < 0x10 || (id != 0x973768 && id != 0xB29EA4))
        return null;
    ushort width  = file.ReadUInt16();
    ushort height = file.ReadUInt16();
    ushort bpp    = file.ReadUInt16();
    return new CgdMetaData {
        Width  = width,
        Height = height,
        BPP    = bpp,
        DataOffset = offset + 0x10 + header_size,
        UnpackedSize = unpacked_size,
        Compression = compression,
        RgbOrder = bpp == 24,
    };
}
```

### GameRes.Formats.KApp.KTool

#### Unpack

```csharp
public static void Unpack (IBinaryStream input, byte[] output, byte method) {
    switch (method)
    {
    case 0: input.Read (output, 0, output.Length); break;
    case 1: DecompressRle (input, output, 1); break;
    case 2: DecompressRle (input, output, 2); break;
    case 3: DecompressRle (input, output, 3); break;
    case 4: DecompressRle (input, output, 4); break;
    case 0x10: DecompressHuffman (input, output); break;
    default:
        throw new InvalidFormatException();
    }
}
```

#### DecompressRle

```csharp
internal static void DecompressRle (IBinaryStream input, byte[] output, int step) {
    for (int i = 0; i < step; ++i)
    {
        sbyte ctl = input.ReadInt8();
        int dst = i;
        while (ctl != 0)
        {
            if (ctl < 0)
            {
                int count = -ctl;
                while (count --> 0)
                {
                    output[dst] = input.ReadUInt8();
                    dst += step;
                }
            }
            else
            {
                byte v = input.ReadUInt8();
                int count = ctl;
                while (count --> 0)
                {
                    output[dst] = v;
                    dst += step;
                }
            }
            ctl = input.ReadInt8();
        }
    }
}
```

#### DecompressHuffman

```csharp
internal static void DecompressHuffman (IBinaryStream input, byte[] output) {
    var decomp = new HuffmanDecoder (input);
    decomp.Unpack (output);
}
```

### GameRes.Formats.KApp.KTool.HuffmanNode

#### 状态与常量

```csharp
public ushort   Code ;

public ushort   LNode ;

public ushort   RNode ;
```

### GameRes.Formats.KApp.KTool.HuffmanDecoder

#### 状态与常量

```csharp
IBinaryStream   m_input ;

HuffmanNode[]   m_tree = new HuffmanNode[514] ;
```

#### HuffmanDecoder

```csharp
public HuffmanDecoder (IBinaryStream input) {
    m_input = input;
}
```

#### Unpack

```csharp
public void Unpack (byte[] output) {
    ReadDict();
    var root = BuildTree();
    int dst = 0;
    int bits = 0;
    byte mask = 0;
    while (dst < output.Length)
    {
        var token = root;
        while (token > 0x100)
        {
            if (0 == mask)
            {
                bits = m_input.ReadByte();
                if (-1 == bits)
                    return;
                mask = 0x80;
            }
            if ((bits & mask) != 0)
                token = m_tree[token].RNode;
            else
                token = m_tree[token].LNode;
            mask >>= 1;
        }
        output[dst++] = (byte)token;
    }
}
```

#### ReadDict

```csharp
void ReadDict () {
    var dict = new byte[256];
    DecompressRle (m_input, dict, 1);
    for (int i = 0; i < 256; ++i)
    {
        m_tree[i].Code = dict[i];
    }
    m_tree[256].Code = 1;
}
```

#### BuildTree

```csharp
ushort BuildTree () {
    m_tree[513].Code = ushort.MaxValue;
    ushort root = 257;
    while (root > 0)
    {
        ushort rhs = 513;
        ushort lhs = 513;
        ushort node = 0;
        for (ushort i = 0; i < root; ++i)
        {
            var code = m_tree[node].Code;
            if (code != 0)
            {
                if (code < m_tree[lhs].Code)
                {
                    rhs = lhs;
                    lhs = i;
                }
                else if (code < m_tree[rhs].Code)
                {
                    rhs = i;
                }
            }
            ++node;
        }
        if (rhs == 513)
            break;
        m_tree[root].Code = (ushort)(m_tree[rhs].Code + m_tree[lhs].Code);
        m_tree[root].LNode = lhs;
        m_tree[root].RNode = rhs;
        m_tree[lhs].Code = 0;
        m_tree[rhs].Code = 0;
        ++root;
    }
    return (ushort)(root - 1);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/KApp/ImageCGD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
