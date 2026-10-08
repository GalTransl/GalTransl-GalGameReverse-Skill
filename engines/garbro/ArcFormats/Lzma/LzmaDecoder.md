# Lzma / LzmaDecoder：归档读取与解码

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

### SevenZip.Compression.LZMA.Decoder

继承/接口：`ICoder`, `ISetDecoderProperties`。

#### 状态与常量

```csharp
LZ.OutWindow m_OutWindow = new LZ.OutWindow() ;

RangeCoder.Decoder m_RangeDecoder = new RangeCoder.Decoder() ;

BitDecoder[] m_IsMatchDecoders = new BitDecoder[Base.kNumStates << Base.kNumPosStatesBitsMax] ;

BitDecoder[] m_IsRepDecoders = new BitDecoder[Base.kNumStates] ;

BitDecoder[] m_IsRepG0Decoders = new BitDecoder[Base.kNumStates] ;

BitDecoder[] m_IsRepG1Decoders = new BitDecoder[Base.kNumStates] ;

BitDecoder[] m_IsRepG2Decoders = new BitDecoder[Base.kNumStates] ;

BitDecoder[] m_IsRep0LongDecoders = new BitDecoder[Base.kNumStates << Base.kNumPosStatesBitsMax] ;

BitTreeDecoder[] m_PosSlotDecoder = new BitTreeDecoder[Base.kNumLenToPosStates] ;

BitDecoder[] m_PosDecoders = new BitDecoder[Base.kNumFullDistances - Base.kEndPosModelIndex] ;

BitTreeDecoder m_PosAlignDecoder = new BitTreeDecoder(Base.kNumAlignBits) ;

LenDecoder m_LenDecoder = new LenDecoder() ;

LenDecoder m_RepLenDecoder = new LenDecoder() ;

LiteralDecoder m_LiteralDecoder = new LiteralDecoder() ;

uint m_DictionarySize ;

uint m_DictionarySizeCheck ;

uint m_PosStateMask ;

bool _solid = false ;
```

#### Decoder

```csharp
public Decoder() {
	m_DictionarySize = 0xFFFFFFFF;
	for (int i = 0; i < Base.kNumLenToPosStates; i++)
		m_PosSlotDecoder[i] = new BitTreeDecoder(Base.kNumPosSlotBits);
}
```

#### SetDictionarySize

```csharp
void SetDictionarySize(uint dictionarySize) {
	if (m_DictionarySize != dictionarySize)
	{
		m_DictionarySize = dictionarySize;
		m_DictionarySizeCheck = Math.Max(m_DictionarySize, 1);
		uint blockSize = Math.Max(m_DictionarySizeCheck, (1 << 12));
		m_OutWindow.Create(blockSize);
	}
}
```

#### SetLiteralProperties

```csharp
void SetLiteralProperties(int lp, int lc) {
	if (lp > 8)
		throw new InvalidParamException();
	if (lc > 8)
		throw new InvalidParamException();
	m_LiteralDecoder.Create(lp, lc);
}
```

#### SetPosBitsProperties

```csharp
void SetPosBitsProperties(int pb) {
	if (pb > Base.kNumPosStatesBitsMax)
		throw new InvalidParamException();
	uint numPosStates = (uint)1 << pb;
	m_LenDecoder.Create(numPosStates);
	m_RepLenDecoder.Create(numPosStates);
	m_PosStateMask = numPosStates - 1;
}
```

#### Init

```csharp
void Init(System.IO.Stream inStream, System.IO.Stream outStream) {
	m_RangeDecoder.Init(inStream);
	m_OutWindow.Init(outStream, _solid);

	uint i;
	for (i = 0; i < Base.kNumStates; i++)
	{
		for (uint j = 0; j <= m_PosStateMask; j++)
		{
			uint index = (i << Base.kNumPosStatesBitsMax) + j;
			m_IsMatchDecoders[index].Init();
			m_IsRep0LongDecoders[index].Init();
		}
		m_IsRepDecoders[i].Init();
		m_IsRepG0Decoders[i].Init();
		m_IsRepG1Decoders[i].Init();
		m_IsRepG2Decoders[i].Init();
	}

	m_LiteralDecoder.Init();
	for (i = 0; i < Base.kNumLenToPosStates; i++)
		m_PosSlotDecoder[i].Init();

	for (i = 0; i < Base.kNumFullDistances - Base.kEndPosModelIndex; i++)
		m_PosDecoders[i].Init();

	m_LenDecoder.Init();
	m_RepLenDecoder.Init();
	m_PosAlignDecoder.Init();
}
```

#### Code

```csharp
public void Code(System.IO.Stream inStream, System.IO.Stream outStream,
	Int64 inSize, Int64 outSize, ICodeProgress progress) {
	Init(inStream, outStream);

	Base.State state = new Base.State();
	state.Init();
	uint rep0 = 0, rep1 = 0, rep2 = 0, rep3 = 0;

	UInt64 nowPos64 = 0;
	UInt64 outSize64 = (UInt64)outSize;
	if (nowPos64 < outSize64)
	{
		if (m_IsMatchDecoders[state.Index << Base.kNumPosStatesBitsMax].Decode(m_RangeDecoder) != 0)
			throw new DataErrorException();
		state.UpdateChar();
		byte b = m_LiteralDecoder.DecodeNormal(m_RangeDecoder, 0, 0);
		m_OutWindow.PutByte(b);
		nowPos64++;
	}
	while (nowPos64 < outSize64)
	{

		{
			uint posState = (uint)nowPos64 & m_PosStateMask;
			if (m_IsMatchDecoders[(state.Index << Base.kNumPosStatesBitsMax) + posState].Decode(m_RangeDecoder) == 0)
			{
				byte b;
				byte prevByte = m_OutWindow.GetByte(0);
				if (!state.IsCharState())
					b = m_LiteralDecoder.DecodeWithMatchByte(m_RangeDecoder,
						(uint)nowPos64, prevByte, m_OutWindow.GetByte(rep0));
				else
					b = m_LiteralDecoder.DecodeNormal(m_RangeDecoder, (uint)nowPos64, prevByte);
				m_OutWindow.PutByte(b);
				state.UpdateChar();
				nowPos64++;
			}
			else
			{
				uint len;
				if (m_IsRepDecoders[state.Index].Decode(m_RangeDecoder) == 1)
				{
					if (m_IsRepG0Decoders[state.Index].Decode(m_RangeDecoder) == 0)
					{
						if (m_IsRep0LongDecoders[(state.Index << Base.kNumPosStatesBitsMax) + posState].Decode(m_RangeDecoder) == 0)
						{
							state.UpdateShortRep();
							m_OutWindow.PutByte(m_OutWindow.GetByte(rep0));
							nowPos64++;
							continue;
						}
					}
					else
					{
						UInt32 distance;
						if (m_IsRepG1Decoders[state.Index].Decode(m_RangeDecoder) == 0)
						{
							distance = rep1;
						}
						else
						{
							if (m_IsRepG2Decoders[state.Index].Decode(m_RangeDecoder) == 0)
								distance = rep2;
							else
							{
								distance = rep3;
								rep3 = rep2;
							}
							rep2 = rep1;
						}
						rep1 = rep0;
						rep0 = distance;
					}
					len = m_RepLenDecoder.Decode(m_RangeDecoder, posState) + Base.kMatchMinLen;
					state.UpdateRep();
				}
				else
				{
					rep3 = rep2;
					rep2 = rep1;
					rep1 = rep0;
					len = Base.kMatchMinLen + m_LenDecoder.Decode(m_RangeDecoder, posState);
					state.UpdateMatch();
					uint posSlot = m_PosSlotDecoder[Base.GetLenToPosState(len)].Decode(m_RangeDecoder);
					if (posSlot >= Base.kStartPosModelIndex)
					{
						int numDirectBits = (int)((posSlot >> 1) - 1);
						rep0 = ((2 | (posSlot & 1)) << numDirectBits);
						if (posSlot < Base.kEndPosModelIndex)
							rep0 += BitTreeDecoder.ReverseDecode(m_PosDecoders,
									rep0 - posSlot - 1, m_RangeDecoder, numDirectBits);
						else
						{
							rep0 += (m_RangeDecoder.DecodeDirectBits(
								numDirectBits - Base.kNumAlignBits) << Base.kNumAlignBits);
							rep0 += m_PosAlignDecoder.ReverseDecode(m_RangeDecoder);
						}
					}
					else
						rep0 = posSlot;
				}
				if (rep0 >= m_OutWindow.TrainSize + nowPos64 || rep0 >= m_DictionarySizeCheck)
				{
					if (rep0 == 0xFFFFFFFF)
						break;
					throw new DataErrorException();
				}
				m_OutWindow.CopyBlock(rep0, len);
				nowPos64 += len;
			}
		}
	}
	m_OutWindow.Flush();
	m_OutWindow.ReleaseStream();
	m_RangeDecoder.ReleaseStream();
}
```

#### SetDecoderProperties

```csharp
public void SetDecoderProperties(byte[] properties) {
	if (properties.Length < 5)
		throw new InvalidParamException();
	int lc = properties[0] % 9;
	int remainder = properties[0] / 9;
	int lp = remainder % 5;
	int pb = remainder / 5;
	if (pb > Base.kNumPosStatesBitsMax)
		throw new InvalidParamException();
	UInt32 dictionarySize = 0;
	for (int i = 0; i < 4; i++)
		dictionarySize += ((UInt32)(properties[1 + i])) << (i * 8);
	SetDictionarySize(dictionarySize);
	SetLiteralProperties(lp, lc);
	SetPosBitsProperties(pb);
}
```

#### Train

```csharp
public bool Train(System.IO.Stream stream) {
	_solid = true;
	return m_OutWindow.Train(stream);
}
```

### SevenZip.Compression.LZMA.Decoder.LenDecoder

#### 状态与常量

```csharp
BitDecoder m_Choice = new BitDecoder() ;

BitDecoder m_Choice2 = new BitDecoder() ;

BitTreeDecoder[] m_LowCoder = new BitTreeDecoder[Base.kNumPosStatesMax] ;

BitTreeDecoder[] m_MidCoder = new BitTreeDecoder[Base.kNumPosStatesMax] ;

BitTreeDecoder m_HighCoder = new BitTreeDecoder(Base.kNumHighLenBits) ;

uint m_NumPosStates = 0 ;
```

#### Create

```csharp
public void Create(uint numPosStates) {
	for (uint posState = m_NumPosStates; posState < numPosStates; posState++)
	{
		m_LowCoder[posState] = new BitTreeDecoder(Base.kNumLowLenBits);
		m_MidCoder[posState] = new BitTreeDecoder(Base.kNumMidLenBits);
	}
	m_NumPosStates = numPosStates;
}
```

#### Init

```csharp
public void Init() {
	m_Choice.Init();
	for (uint posState = 0; posState < m_NumPosStates; posState++)
	{
		m_LowCoder[posState].Init();
		m_MidCoder[posState].Init();
	}
	m_Choice2.Init();
	m_HighCoder.Init();
}
```

#### Decode

```csharp
public uint Decode(RangeCoder.Decoder rangeDecoder, uint posState) {
	if (m_Choice.Decode(rangeDecoder) == 0)
		return m_LowCoder[posState].Decode(rangeDecoder);
	else
	{
		uint symbol = Base.kNumLowLenSymbols;
		if (m_Choice2.Decode(rangeDecoder) == 0)
			symbol += m_MidCoder[posState].Decode(rangeDecoder);
		else
		{
			symbol += Base.kNumMidLenSymbols;
			symbol += m_HighCoder.Decode(rangeDecoder);
		}
		return symbol;
	}
}
```

### SevenZip.Compression.LZMA.Decoder.LiteralDecoder

#### 状态与常量

```csharp
Decoder2[] m_Coders ;

int m_NumPrevBits ;

int m_NumPosBits ;

uint m_PosMask ;
```

#### Create

```csharp
public void Create(int numPosBits, int numPrevBits) {
	if (m_Coders != null && m_NumPrevBits == numPrevBits &&
		m_NumPosBits == numPosBits)
		return;
	m_NumPosBits = numPosBits;
	m_PosMask = ((uint)1 << numPosBits) - 1;
	m_NumPrevBits = numPrevBits;
	uint numStates = (uint)1 << (m_NumPrevBits + m_NumPosBits);
	m_Coders = new Decoder2[numStates];
	for (uint i = 0; i < numStates; i++)
		m_Coders[i].Create();
}
```

#### Init

```csharp
public void Init() {
	uint numStates = (uint)1 << (m_NumPrevBits + m_NumPosBits);
	for (uint i = 0; i < numStates; i++)
		m_Coders[i].Init();
}
```

#### GetState

```csharp
uint GetState(uint pos, byte prevByte) { return ((pos & m_PosMask) << m_NumPrevBits) + (uint)(prevByte >> (8 - m_NumPrevBits)); }
```

#### DecodeNormal

```csharp
public byte DecodeNormal(RangeCoder.Decoder rangeDecoder, uint pos, byte prevByte) { return m_Coders[GetState(pos, prevByte)].DecodeNormal(rangeDecoder); }
```

#### DecodeWithMatchByte

```csharp
public byte DecodeWithMatchByte(RangeCoder.Decoder rangeDecoder, uint pos, byte prevByte, byte matchByte) { return m_Coders[GetState(pos, prevByte)].DecodeWithMatchByte(rangeDecoder, matchByte); }
```

### SevenZip.Compression.LZMA.Decoder.LiteralDecoder.Decoder2

#### 状态与常量

```csharp
BitDecoder[] m_Decoders ;
```

#### Create

```csharp
public void Create() { m_Decoders = new BitDecoder[0x300]; }
```

#### Init

```csharp
public void Init() { for (int i = 0; i < 0x300; i++) m_Decoders[i].Init(); }
```

#### DecodeNormal

```csharp
public byte DecodeNormal(RangeCoder.Decoder rangeDecoder) {
	uint symbol = 1;
	do
		symbol = (symbol << 1) | m_Decoders[symbol].Decode(rangeDecoder);
	while (symbol < 0x100);
	return (byte)symbol;
}
```

#### DecodeWithMatchByte

```csharp
public byte DecodeWithMatchByte(RangeCoder.Decoder rangeDecoder, byte matchByte) {
	uint symbol = 1;
	do
	{
		uint matchBit = (uint)(matchByte >> 7) & 1;
		matchByte <<= 1;
		uint bit = m_Decoders[((1 + matchBit) << 8) + symbol].Decode(rangeDecoder);
		symbol = (symbol << 1) | bit;
		if (matchBit != bit)
		{
			while (symbol < 0x100)
				symbol = (symbol << 1) | m_Decoders[symbol].Decode(rangeDecoder);
			break;
		}
	}
	while (symbol < 0x100);
	return (byte)symbol;
}
```

## 配套算法与外部条件

- [ArcFormats/Lzma/ICoder.cs](ICoder.md)：本页引用的随包算法资料。
- [ArcFormats/Lzma/LzmaBase.cs](LzmaBase.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Lzma/LzmaDecoder.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
