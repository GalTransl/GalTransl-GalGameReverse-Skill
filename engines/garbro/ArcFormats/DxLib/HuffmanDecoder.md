# DxLib / HuffmanDecoder：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DxLib.DXA8HuffmanNode

#### 状态与常量

```csharp
public UInt64 Weight ;

public int bitNumber ;

public byte[] bitArray ;

public int Index ;

public int ParentNode ;

public int[] ChildNode ;
```

#### DXA8HuffmanNode

```csharp
internal DXA8HuffmanNode() {
    bitArray = new byte[32];
    ChildNode = new int[2];
}
```

### GameRes.Formats.DxLib.HuffmanDecoder

#### 状态与常量

```csharp
byte[]          m_input ;

byte[]          m_output ;

int             m_src ;

byte             m_bits ;

int             m_bit_count ;

ulong m_readBytes ;

byte m_readBits ;

DXA8HuffmanNode[] nodes ;

ulong originalSize ;

ulong compressedSize ;

ulong headerSize ;

ulong srcSize ;
```

#### HuffmanDecoder

```csharp
public HuffmanDecoder (byte[] src,ulong srcSize) {
    m_input = src;
    m_output = null;

    this.srcSize = srcSize;
    m_src = 0;
    m_bit_count = 0;
    m_readBytes = 0;
    m_readBits = 0;
    originalSize = compressedSize = headerSize = 0;
    ushort[] weights = new ushort[256];
    nodes = new DXA8HuffmanNode[256+255];
    for (int i = 0; i < nodes.Length; i++)
    {
        nodes[i] = new DXA8HuffmanNode();
    }
}
```

#### Unpack

```csharp
public byte[] Unpack () {

    for (int i=0; i<nodes.Length; i++)
    {
        nodes[i].ParentNode = -1;
        nodes[i].ChildNode[0] = -1;
        nodes[i].ChildNode[1] = -1;
    }
    SetupWeights();

    if (srcSize!=(compressedSize+headerSize))
    {
        throw new FileSizeException(String.Format("Supplied srcSize does not match with compressedSize+headerSize. Expected {0} got {1}",compressedSize+headerSize,srcSize));
    }
    m_output = new byte[originalSize];
    CreateTree();
    PopulateDataNodes();
    DoUnpack();
    return m_output;
}
```

#### DoUnpack

```csharp
private void DoUnpack() {
    var targetSize = originalSize;
    byte[] compressedData = new byte[compressedSize];
    Array.Copy(m_input, (long)headerSize, compressedData, 0, (long)(compressedSize));

    int PressBitCounter=0, PressBitData=0, Index=0, NodeIndex=0;
    int PressSizeCounter = 0;
    ulong DestSizeCounter = 0;
    int[] NodeIndexTable=new int[512];
    {
        ushort[] bitMask = new ushort[9];
        for (int i = 0; i < 9; i++)
        {
            bitMask[i] = (ushort)((1<<i+1) - 1);
        }

        for (int i = 0; i < 512; i++)
        {
            NodeIndexTable[i] = -1;

            for (int j = 0; j < 256 + 254; j++)
            {
                ushort BitArrayFirstBatch;
                if (nodes[j].bitNumber > 9) continue;

                BitArrayFirstBatch = (ushort)(nodes[j].bitArray[0] | (nodes[j].bitArray[1] << 8));

                if ((i & bitMask[nodes[j].bitNumber - 1]) == (BitArrayFirstBatch & bitMask[nodes[j].bitNumber-1]))
                {
                    NodeIndexTable[i] = j;
                    break;
                }
            }

        }

    }
    PressBitData = compressedData[PressBitCounter];

    for (DestSizeCounter = 0;DestSizeCounter < originalSize; DestSizeCounter++)
    {
        if (DestSizeCounter>= originalSize - 17)
        {
            NodeIndex = 510;
        }
        else
        {
            if (PressBitCounter==8)
            {
                PressSizeCounter++;
                PressBitData = compressedData[PressSizeCounter];
                PressBitCounter = 0;
            }

            PressBitData = (PressBitData | (compressedData[PressSizeCounter+1]<<(8-PressBitCounter))) & 0x1ff;
            NodeIndex = NodeIndexTable[PressBitData];
            PressBitCounter += nodes[NodeIndex].bitNumber;
            if (PressBitCounter >= 16)
            {
                PressSizeCounter += 2;
                PressBitCounter -= 16;
                PressBitData = compressedData[PressSizeCounter] >> PressBitCounter;
            }
            else if (PressBitCounter >=8)
            {
                PressSizeCounter ++;
                PressBitCounter -= 8;
                PressBitData = compressedData[PressSizeCounter] >> PressBitCounter;
            }
            else
            {
                PressBitData >>= nodes[NodeIndex].bitNumber;
            }
        }

        while (NodeIndex > 255)
        {
            if (PressBitCounter == 8)
            {
                PressSizeCounter++;
                PressBitData = compressedData[PressSizeCounter];
                PressBitCounter = 0;
            }
            Index = PressBitData & 1;
            PressBitData >>= 1;
            PressBitCounter++;
            NodeIndex = nodes[NodeIndex].ChildNode[Index];
        }
        m_output[DestSizeCounter] = (byte)NodeIndex;
    }

}
```

#### PopulateDataNodes

```csharp
private void PopulateDataNodes() {

    byte[] ScratchSpace = new byte[32];
    int TempBitIndex, TempBitCount;

    for (int i = 0; i < 256 + 254; i++)
    {
        nodes[i].bitNumber = 0;
        TempBitIndex = 0;
        TempBitCount = 0;
        ScratchSpace[TempBitIndex] = 0;

        for (int j = i; nodes[j].ParentNode!=-1;j = nodes[j].ParentNode)
        {
            if (TempBitCount == 8)
            {
                TempBitCount = 0;
                TempBitIndex++;
                ScratchSpace[TempBitIndex] = 0;
            }
            ScratchSpace[TempBitIndex] <<= 1;
            ScratchSpace[TempBitIndex] |= (byte)nodes[j].Index;
            TempBitCount++;
            nodes[i].bitNumber++;

        }

        int BitIndex=0, BitCount=0;
        nodes[i].bitArray[BitIndex] = 0;
        while (TempBitIndex >= 0)
        {
            if (BitCount == 8)
            {
                BitCount = 0;
                BitIndex++;
                nodes[i].bitArray[BitIndex] = 0;
            }
            nodes[i].bitArray[BitIndex] |= (byte)((ScratchSpace[TempBitIndex] & 1) << BitCount);
            ScratchSpace[TempBitIndex] >>= 1;
            TempBitCount--;
            if (TempBitCount == 0)
            {
                TempBitIndex--;
                TempBitCount = 8;
            }
            BitCount++;
        }
    }

}
```

#### SetupWeights

```csharp
private void SetupWeights() {
    int sizeA, sizeB;
    byte BitNum;
    byte Minus;
    ushort SaveData;
    ushort[] weights = new ushort[256];
    sizeA = (int)GetBits(6) + 1;
    originalSize = GetBits(sizeA);
    sizeB = (int)GetBits(6)+1;
    compressedSize = GetBits(sizeB);

    BitNum = (byte)(((int)GetBits(3) + 1) * 2);
    Minus = (byte)GetBits(1);
    SaveData = (ushort)GetBits(BitNum);
    weights[0] = SaveData;
    for (int i = 1; i < 256; i++)
    {
        BitNum = (byte)(((int)GetBits(3) + 1) * 2);
        Minus = (byte)GetBits(1);
        SaveData = (ushort)GetBits(BitNum);
        weights[i] = (ushort)(Minus == 1 ? weights[i - 1] - SaveData : weights[i - 1] + SaveData);
    }
    headerSize = GetReadBytes();
    for (int i = 0;i < 256; i++)
    {
        nodes[i].Weight = weights[i];
    }

}
```

#### CreateTree

```csharp
void CreateTree() {
    int NodeNum=256, DataNum=256;

    while (DataNum > 1)
    {
        int MinNode1 = -1;
        int MinNode2 = -1;
        int NodeIndex = 0;

        for (int i = 0; i < DataNum; NodeIndex++) {

            if (nodes[NodeIndex].ParentNode != -1) continue;
            i++;

            if (MinNode1 == -1 || nodes[MinNode1].Weight > nodes[NodeIndex].Weight)
            {
                {
                    MinNode2 = MinNode1;
                    MinNode1 = NodeIndex;
                }
            } else if (MinNode2 == -1 || nodes[MinNode2].Weight > nodes[NodeIndex].Weight)
            {
                MinNode2 = NodeIndex;
            }
        }
        nodes[NodeNum].ParentNode = -1;
        nodes[NodeNum].Weight = nodes[MinNode1].Weight + nodes[MinNode2].Weight;
        nodes[NodeNum].ChildNode[0] = MinNode1;
        nodes[NodeNum].ChildNode[1] = MinNode2;
        nodes[MinNode1].Index = 0;
        nodes[MinNode2].Index = 1;
        nodes[MinNode1].ParentNode = NodeNum;
        nodes[MinNode2].ParentNode = NodeNum;

        NodeNum++;
        DataNum--;
    }
}
```

#### GetBits

```csharp
ulong GetBits (int count) {
    ulong bits = 0;
    for (int i = 0; i < count;i++)
    {
        if (0 == m_bit_count)
        {
            m_bits = m_input[m_src];
            m_src++;
            m_bit_count = 8;
        }

        bits |= ((ulong)((m_bits >> (7 - m_readBits)) & 1)) <<(count-1-i);
        --m_bit_count;
        m_readBits++;
        if (m_readBits ==8)
        {
            m_readBits = 0;
            m_readBytes++;
        }
    }
    return bits;
}
```

#### GetReadBytes

```csharp
ulong GetReadBytes() {
    return m_readBytes + (m_readBits != 0 ? 1ul : 0ul);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/DxLib/HuffmanDecoder.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
