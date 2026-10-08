# HuneX / Decoder：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `LenZuDecoder.LenZuDecoder` | `m_unpacked = new byte[BitConverter.ToUInt32(buffer, 0)];` |
| `LenZuDecoder.ReadIntVL` | `return BitConverter.ToInt32(buffer, 0);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.HuneX.HuffmanTree

#### 状态与常量

```csharp
List<HuffmanNode> m_table ;

bool m_invert ;
```

#### HuffmanTree

```csharp
public HuffmanTree(int[] weights, bool invert = false) {
    m_table = new List<HuffmanNode>(weights.Length);

    for (int i = 0; i < weights.Length; i++) {
        m_table.Add(new HuffmanNode {
            Index = i,
            Weight = weights[i]
        });
    }

    m_invert = invert;
}
```

#### Build

```csharp
public void Build(int max_entries) {
    int total_weight = m_table.Sum(x => x.Weight);
    for (int i = m_table.Count; i < max_entries; i++) {
        HuffmanNode child0 = null, child1 = null;
        for (int j = 0; j < i; j++) {
            var node = m_table[j];
            if (node.Weight == 0 || node.Parent != null)
                continue;
            if (child0 == null || node.Weight < child0.Weight) {
                child1 = child0;
                child0 = node;
            }
            else if (child1 == null || node.Weight < child1.Weight) {
                child1 = node;
            }
        }
        var parent = new HuffmanNode();
        if (m_invert) {
            SetNodeRelation(parent, child1, child0);
        }
        else {
            SetNodeRelation(parent, child0, child1);
        }
        m_table.Add(parent);
        if (parent.Weight >= total_weight)
            break;
    }
}
```

#### DecodeSequence

```csharp
public int DecodeSequence(IBitStream input) {
    HuffmanNode node = m_table[m_table.Count - 1];

    while (node.Child0 != null || node.Child1 != null) {
        int bit = input.GetNextBit();
        node = bit > 0 ? node.Child1 : node.Child0;
    }

    return node.Index;
}
```

#### SetNodeRelation

```csharp
void SetNodeRelation(HuffmanNode parent, HuffmanNode child0, HuffmanNode child1) {
    if (child0 != null) {
        parent.Child0 = child0;
        child0.Parent = parent;
        parent.Weight += child0.Weight;
    }
    if (child1 != null) {
        parent.Child1 = child1;
        child1.Parent = parent;
        parent.Weight += child1.Weight;
    }
}
```

### GameRes.Formats.HuneX.HuffmanTree.HuffmanNode

#### 状态与常量

```csharp
public int Weight ;

public int Index ;

public HuffmanNode Parent ;

public HuffmanNode Child0 ;

public HuffmanNode Child1 ;
```

### GameRes.Formats.HuneX.LenZuSettings

#### 状态与常量

```csharp
public byte HuffmanTableBitCount ;

public byte BackrefLowBitCount ;

public byte BackrefBaseDistance ;
```

### GameRes.Formats.HuneX.LenZuDecoder

#### 状态与常量

```csharp
Stream m_input ;

byte[] m_unpacked ;

LenZuSettings m_settings ;
```

#### LenZuDecoder

```csharp
public LenZuDecoder(byte[] buffer) {
    m_unpacked = new byte[BitConverter.ToUInt32(buffer, 0)];
    m_settings = new LenZuSettings {
        HuffmanTableBitCount = Math.Max(buffer[0x11], buffer[0x12]),
        BackrefLowBitCount = buffer[0x14],
        BackrefBaseDistance = buffer[0x15]
    };
    m_input = new MemoryStream(buffer.Skip(0x16).ToArray());
}
```

#### Unpack

```csharp
public byte[] Unpack() {
    int offset = 0;
    int first_real_entry = 1 << m_settings.HuffmanTableBitCount;
    int index_bits = (m_settings.HuffmanTableBitCount + 7) / 8;
    int index_bytes = (index_bits + 7) / 8;
    int fill_entries = ReadIntVL(index_bytes);
    if (fill_entries == 0)
        fill_entries = first_real_entry;
    var weights = new int[first_real_entry];
    if (first_real_entry * 4 < (index_bits + 4) * fill_entries) {
        fill_entries = first_real_entry;
        for (int i = 0; i < fill_entries; i++) {
            weights[i] = ReadIntVL();
        }
    }
    else {
        for (int i = 0; i < fill_entries; i++) {
            int idx = ReadIntVL(index_bytes);
            weights[idx] = ReadIntVL();
        }
    }
    var tree = new HuffmanTree(weights, true);
    tree.Build(((first_real_entry + 1) * first_real_entry) >> 1);
    using (var input = new MsbBitStream(m_input, true)) {
        while (offset < m_unpacked.Length) {
            int isBackRef = input.GetNextBit();
            if (isBackRef == -1)
                break;
            int length = tree.DecodeSequence(input);
            if (isBackRef > 0) {
                length += m_settings.BackrefBaseDistance;
                int distanceHighBits = tree.DecodeSequence(input);
                int distanceLowBits = m_settings.BackrefLowBitCount > 0
                                    ? input.GetBits(m_settings.BackrefLowBitCount) : 0;
                int distance = (distanceLowBits
                             | (distanceHighBits << m_settings.BackrefLowBitCount))
                             + m_settings.BackrefBaseDistance;
                for (int i = 0; i < length; i++) {
                    m_unpacked[offset] = m_unpacked[offset - distance];
                    offset++;
                }
            }
            else {
                for (int i = 0; i < length + 1; i++) {
                    m_unpacked[offset++] = (byte)input.GetBits(8);
                }
            }
        }
        return m_unpacked;
    }
}
```

#### ReadIntVL

```csharp
int ReadIntVL(int length = sizeof(int)) {
    var buffer = new byte[Math.Max(sizeof(int), length)];
    m_input.Read(buffer, 0, length);
    return BitConverter.ToInt32(buffer, 0);
}
```

## 配套算法与外部条件

- [ArcFormats/BitStream.cs](../BitStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/HuneX/Decoder.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
