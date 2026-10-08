# Entis / ErisaNemesis：归档读取与解码

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

### GameRes.Formats.Entis.NemesisDecodeContext

继承/接口：`ProbDecodeContext`。

#### 状态与常量

```csharp
int         m_iLastSymbol ;

int         m_nNemesisLeft ;

int         m_nNemesisNext ;

byte[]      m_pNemesisBuf ;

int         m_nNemesisIndex ;

bool        m_flagEOF ;

ErisaProbBase           m_pProbERISA ;

NemesisPhraseLookup[]   m_pNemesisLookup ;

byte[]                  m_bytLastSymbol = new byte[4] ;
```

#### NemesisDecodeContext

```csharp
public NemesisDecodeContext (uint buffer_size = 0x10000) : base (buffer_size) {
    m_flagEOF = false;
}
```

#### PrepareToDecodeERISANCode

```csharp
public void PrepareToDecodeERISANCode () {
    if (null == m_pProbERISA)
        m_pProbERISA = new ErisaProbBase();

    m_iLastSymbol = 0;
    for (int i = 0; i < 4; ++i)
        m_bytLastSymbol[i] = 0;

    m_pProbERISA.dwWorkUsed = 0;
    m_pProbERISA.epmBaseModel.Initialize();

    for (int i = 0; i < ErisaProbBase.SlotMax; ++i)
    {
        m_pProbERISA.ptrProbIndex[i] = new ErisaProbModel();
    }
    PrepareToDecodeERISACode();

    if (null == m_pNemesisBuf)
    {
        m_pNemesisBuf = new byte[Nemesis.BufSize];
    }
    if (null == m_pNemesisLookup)
    {
        m_pNemesisLookup = new NemesisPhraseLookup[0x100];
    }
    for (int i = 0; i < m_pNemesisBuf.Length; ++i)
        m_pNemesisBuf[i] = 0;
    for (int i = 0; i < m_pNemesisLookup.Length; ++i)
        m_pNemesisLookup[i] = new NemesisPhraseLookup();
    m_nNemesisIndex = 0;

    m_nNemesisLeft = 0;
    m_flagEOF = false;
}
```

#### DecodeBytes

```csharp
public override uint DecodeBytes (Array ptrDst, uint nCount) {
    return DecodeNemesisCodeBytes (ptrDst as byte[], 0, nCount);
}
```

#### DecodeNemesisCodeBytes

```csharp
public uint DecodeNemesisCodeBytes (byte[] ptrDst, int dst, uint nCount) {
    if (m_flagEOF)
        return 0;

    ErisaProbBase pBase = m_pProbERISA;
    uint nDecoded = 0;
    byte bytSymbol;
    while (nDecoded < nCount)
    {
        if (m_nNemesisLeft > 0)
        {
            uint nNemesisCount = (uint)m_nNemesisLeft;
            if (nNemesisCount > nCount - nDecoded)
            {
                nNemesisCount = nCount - nDecoded;
            }
            byte bytLastSymbol = m_pNemesisBuf[(m_nNemesisIndex - 1) & Nemesis.BufMask];

            for (uint i = 0; i < nNemesisCount; ++i)
            {
                bytSymbol = bytLastSymbol;
                if (m_nNemesisNext >= 0)
                {
                    bytSymbol = m_pNemesisBuf[m_nNemesisNext++];
                    m_nNemesisNext &= Nemesis.BufMask;
                }
                m_bytLastSymbol[m_iLastSymbol++] = bytSymbol;
                m_iLastSymbol &= 3;

                var phrase = m_pNemesisLookup[bytSymbol];
                phrase.index[phrase.first] = (uint)m_nNemesisIndex;
                phrase.first = (phrase.first + 1) & Nemesis.IndexMask;
                bytLastSymbol = bytSymbol;

                m_pNemesisBuf[m_nNemesisIndex++] = bytSymbol;
                m_nNemesisIndex &= Nemesis.BufMask;

                ptrDst[dst++] = bytSymbol;
            }
            m_nNemesisLeft -= (int)nNemesisCount;
            nDecoded += nNemesisCount;
            continue;
        }

        int iDeg;
        ErisaProbModel pModel = pBase.epmBaseModel;
        for (iDeg = 0; iDeg < 4; ++iDeg)
        {
            int iLast = m_bytLastSymbol[(m_iLastSymbol + 3 - iDeg) & 3]
                        >> ErisaProbBase.m_nShiftCount[iDeg];
            if (pModel.SubModel[iLast].Symbol < 0)
            {
                break;
            }
            if ((uint)pModel.SubModel[iLast].Symbol >= pBase.dwWorkUsed)
                throw new InvalidFormatException ("Invalid Nemesis encoding sequence");
            pModel = pBase.ptrProbIndex[pModel.SubModel[iLast].Symbol];
        }
        int iSym = DecodeERISACodeIndex (pModel);
        if (iSym < 0)
        {
            return nDecoded;
        }
        int nSymbol = pModel.SymTable[iSym].Symbol;
        int iSymIndex = pModel.IncreaseSymbol (iSym);

        bool fNemesis = false;
        if (nSymbol == ErisaProbModel.EscCode)
        {
            if (pModel != pBase.epmBaseModel)
            {
                iSym = DecodeERISACodeIndex (pBase.epmBaseModel);
                if (iSym < 0)
                {
                    return  nDecoded;
                }
                nSymbol = pBase.epmBaseModel.SymTable[iSym].Symbol;
                pBase.epmBaseModel.IncreaseSymbol (iSym);
                if (nSymbol != ErisaProbModel.EscCode)
                {
                    pModel.AddSymbol ((short)nSymbol);
                }
                else
                {
                    fNemesis = true;
                }
            }
            else
            {
                fNemesis = true;
            }
        }
        if (fNemesis)
        {
            int nLength, nPhraseIndex;
            nPhraseIndex = DecodeERISACode (m_pPhraseIndexProb);
            if (nPhraseIndex == ErisaProbModel.EscCode)
            {
                m_flagEOF = true;
                return nDecoded;
            }
            if (0 == nPhraseIndex)
            {
                nLength = DecodeERISACode (m_pRunLenProb);
            }
            else
            {
                nLength = DecodeERISACode (m_pPhraseLenProb);
            }
            if (nLength == ErisaProbModel.EscCode)
            {
                return  nDecoded;
            }
            byte bytLastSymbol = m_pNemesisBuf[(m_nNemesisIndex - 1) & Nemesis.BufMask];
            var phrase = m_pNemesisLookup[bytLastSymbol];
            m_nNemesisLeft = nLength;
            if (0 == nPhraseIndex)
            {
                m_nNemesisNext = -1;
            }
            else
            {
                m_nNemesisNext = (int)phrase.index[(phrase.first - nPhraseIndex) & Nemesis.IndexMask];
                if (m_pNemesisBuf[m_nNemesisNext] != bytLastSymbol)
                    throw new InvalidFormatException ("Invalid Nemesis encoding sequence");
                m_nNemesisNext = (m_nNemesisNext + 1) & Nemesis.BufMask;
            }
            continue;
        }
        bytSymbol = (byte)nSymbol;
        m_bytLastSymbol[m_iLastSymbol++] = bytSymbol;
        m_iLastSymbol &= 3;

        var ppl = m_pNemesisLookup[bytSymbol];
        ppl.index[ppl.first] = (uint)m_nNemesisIndex;
        ppl.first = (ppl.first + 1) & Nemesis.IndexMask;
        m_pNemesisBuf[m_nNemesisIndex++] = bytSymbol;
        m_nNemesisIndex &= Nemesis.BufMask;

        ptrDst[dst++] = bytSymbol;
        nDecoded++;

        if ((pBase.dwWorkUsed < ErisaProbBase.SlotMax) && (iDeg < 4))
        {
            int iSymbol = bytSymbol >> ErisaProbBase.m_nShiftCount[iDeg];
            if (iSymbol >= ErisaProbModel.SubSortMax)
                throw new InvalidFormatException ("Invalid Nemesis encoding sequence");
            if (++pModel.SubModel[iSymbol].Occured >= ErisaProbBase.m_nNewProbLimit[iDeg])
            {
                int i;
                ErisaProbModel pParent = pModel;
                pModel = pBase.epmBaseModel;
                for (i = 0; i <= iDeg; ++i)
                {
                    iSymbol = m_bytLastSymbol[(m_iLastSymbol + 3 - i) & 3]
                              >> ErisaProbBase.m_nShiftCount[i];
                    if (pModel.SubModel[iSymbol].Symbol < 0)
                    {
                        break;
                    }
                    if ((uint)pModel.SubModel[iSymbol].Symbol >= pBase.dwWorkUsed)
                        throw new InvalidFormatException ("Invalid Nemesis encoding sequence");
                    pModel = pBase.ptrProbIndex[pModel.SubModel[iSymbol].Symbol];
                }
                if ((i <= iDeg) && (pModel.SubModel[iSymbol].Symbol < 0))
                {
                    ErisaProbModel pNew = pBase.ptrProbIndex[pBase.dwWorkUsed];
                    pModel.SubModel[iSymbol].Symbol = (short)(pBase.dwWorkUsed++);

                    pNew.TotalCount = 0;
                    int j = 0;
                    for (i = 0; i < (int)pParent.SymbolSorts; ++i)
                    {
                        ushort wOccured = (ushort)(pParent.SymTable[i].Occured >> 4);
                        if (wOccured > 0 && (pParent.SymTable[i].Symbol != ErisaProbModel.EscCode))
                        {
                            pNew.TotalCount += wOccured;
                            pNew.SymTable[j].Occured = wOccured;
                            pNew.SymTable[j].Symbol = pParent.SymTable[i].Symbol;
                            j++;
                        }
                    }
                    pNew.TotalCount++;
                    pNew.SymTable[j].Occured = 1;
                    pNew.SymTable[j].Symbol = ErisaProbModel.EscCode;
                    pNew.SymbolSorts = ++j;

                    for (i = 0; i < ErisaProbModel.SubSortMax; ++i)
                    {
                        pNew.SubModel[i].Occured = 0;
                        pNew.SubModel[i].Symbol = -1;
                    }
                }
            }
        }
    }
    return nDecoded;
}
```

### GameRes.Formats.Entis.ErisaProbBase

#### 状态与常量

```csharp
public uint                 dwWorkUsed ;

public ErisaProbModel       epmBaseModel = new ErisaProbModel() ;

public ErisaProbModel[]     ptrProbIndex = new ErisaProbModel[SlotMax] ;

public const int SlotMax = 0x800 ;

public static readonly int[] m_nShiftCount = { 1, 3, 4, 5 }

public static readonly int[] m_nNewProbLimit = { 0x01, 0x08, 0x10, 0x20 }
```

### GameRes.Formats.Entis.Nemesis

#### 状态与常量

```csharp
public const int BufSize = 0x10000 ;

public const int BufMask = 0xFFFF ;

public const int IndexLimit  = 0x100 ;

public const int IndexMask   = 0xFF ;
```

### GameRes.Formats.Entis.NemesisPhraseLookup

#### 状态与常量

```csharp
public uint     first ;

public uint[]   index = new uint[Nemesis.IndexLimit] ;
```

### GameRes.Formats.Entis.ErisaNemesisStream

继承/接口：`InputProxyStream`。

#### 状态与常量

```csharp
NemesisDecodeContext    m_decoder ;

int                     m_remaining ;

bool                    m_eof = false ;

public override bool CanSeek { get { return false; } }

public override long Length { get { throw new NotSupportedException(); } }

public override long Position {
    get { throw new NotSupportedException(); }
    set { throw new NotSupportedException(); }
}
```

#### ErisaNemesisStream

```csharp
public ErisaNemesisStream (Stream input, int output_length = 0) : base (input) {
    m_decoder = new NemesisDecodeContext();
    m_decoder.AttachInputFile (input);
    m_decoder.PrepareToDecodeERISANCode();
    m_remaining = output_length > 0 ? output_length : int.MaxValue;
}
```

#### Read

```csharp
public override int Read (byte[] buffer, int offset, int count) {
    int read = 0;
    if (!m_eof && m_remaining > 0)
    {
        uint chunk_size = (uint)Math.Min (count, m_remaining);
        read = (int)m_decoder.DecodeNemesisCodeBytes (buffer, offset, chunk_size);
        m_eof = read < count;
        m_remaining -= read;
    }
    return read;
}
```

#### Seek

```csharp
public override long Seek (long offset, SeekOrigin origin) {
    throw new NotSupportedException();
}
```

## 配套算法与外部条件

- [ArcFormats/Entis/EriReader.cs](EriReader.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Entis/ErisaNemesis.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
