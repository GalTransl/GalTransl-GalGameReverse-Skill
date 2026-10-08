# KiriKiri / KiriKiriCx：归档读取与解码

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

### 枚举值

```csharp
enum CxByteCode
    {
        NOP,
        RETN,
        MOV_EDI_ARG,
        PUSH_EBX,
        POP_EBX,
        PUSH_ECX,
        POP_ECX,
        MOV_EAX_EBX,
        MOV_EBX_EAX,
        MOV_ECX_EBX,
        MOV_EAX_CONTROL_BLOCK,
        MOV_EAX_EDI,
        MOV_EAX_INDIRECT,
        ADD_EAX_EBX,
        SUB_EAX_EBX,
        IMUL_EAX_EBX,
        AND_ECX_0F,
        SHR_EBX_1,
        SHL_EAX_1,
        SHR_EAX_CL,
        SHL_EAX_CL,
        OR_EAX_EBX,
        NOT_EAX,
        NEG_EAX,
        DEC_EAX,
        INC_EAX,

        IMMED = 0x100,
        MOV_EAX_IMMED,
        AND_EBX_IMMED,
        AND_EAX_IMMED,
        XOR_EAX_IMMED,
        ADD_EAX_IMMED,
        SUB_EAX_IMMED,
    }
```

### GameRes.Formats.KiriKiri.CxProgramException

继承/接口：`ApplicationException`。

### GameRes.Formats.KiriKiri.CxScheme

#### 状态与常量

```csharp
public uint     Mask ;

public uint     Offset ;

public byte[]   PrologOrder ;

public byte[]   OddBranchOrder ;

public byte[]   EvenBranchOrder ;

public uint[]   ControlBlock ;

public string   TpmFileName ;
```

### GameRes.Formats.KiriKiri.CxEncryption

继承/接口：`ICrypt`。

#### 状态与常量

```csharp
protected uint  m_mask ;

protected uint  m_offset ;

protected byte[]     PrologOrder ;

protected byte[]  OddBranchOrder ;

protected byte[] EvenBranchOrder ;

protected uint[] ControlBlock ;

protected string TpmFileName ;

[NonSerialized]
CxProgram[] m_program_list = new CxProgram[0x80] ;

static readonly byte[] s_ctl_block_signature = Encoding.ASCII.GetBytes (" Encryption control block") ;
```

#### OnDeserialized

```csharp
[OnDeserialized()]
void PostDeserialization (StreamingContext context) {
    m_program_list = new CxProgram[0x80];
}
```

#### CxEncryption

```csharp
public CxEncryption (CxScheme scheme) {
    m_mask = scheme.Mask;
    m_offset = scheme.Offset;

    PrologOrder = scheme.PrologOrder;
    OddBranchOrder = scheme.OddBranchOrder;
    EvenBranchOrder = scheme.EvenBranchOrder;

    ControlBlock = scheme.ControlBlock;
    TpmFileName = scheme.TpmFileName;
}
```

#### Init

```csharp
public override void Init (ArcFile arc) {
    if (ControlBlock != null)
        return;
    if (string.IsNullOrEmpty (TpmFileName))
        throw new InvalidEncryptionScheme();

    var dir_name = VFS.GetDirectoryName (arc.File.Name);
    var tpm_name = VFS.CombinePath (dir_name, TpmFileName);

    if (!VFS.FileExists (tpm_name))
        tpm_name = VFS.CombinePath (VFS.CombinePath (dir_name, "plugin"), TpmFileName);
    using (var tpm = VFS.OpenView (tpm_name))
    {
        if (tpm.MaxOffset < 0x1000 || tpm.MaxOffset > uint.MaxValue)
            throw new InvalidEncryptionScheme ("Invalid KiriKiri TPM plugin");
        using (var view = tpm.CreateViewAccessor (0, (uint)tpm.MaxOffset))
        unsafe
        {
            byte* begin = view.GetPointer (0);
            byte* end   = begin + (((uint)tpm.MaxOffset - 0x1000u) & ~0x3u);
            try {
                while (begin < end)
                {
                    int i;
                    for (i = 0; i < s_ctl_block_signature.Length; ++i)
                    {
                        if (begin[i] != s_ctl_block_signature[i])
                            break;
                    }
                    if (s_ctl_block_signature.Length == i)
                    {
                        ControlBlock = new uint[0x400];
                        uint* src = (uint*)begin;
                        for (i = 0; i < ControlBlock.Length; ++i)
                            ControlBlock[i] = ~src[i];
                        return;
                    }
                    begin += 4;
                }
                throw new InvalidEncryptionScheme ("No control block found inside TPM plugin");
            }
            finally {
                view.SafeMemoryMappedViewHandle.ReleasePointer();
            }
        }
    }
}
```

#### GetBaseOffset

```csharp
uint GetBaseOffset (uint hash) {
    return (hash & m_mask) + m_offset;
}
```

#### Decrypt

```csharp
public override byte Decrypt (Xp3Entry entry, long offset, byte value) {
    uint key = entry.Hash;
    uint base_offset = GetBaseOffset (key);
    if (offset >= base_offset)
    {
        key = (key >> 16) ^ key;
    }
    var buffer = new byte[1] { value };
    Decode (key, offset, buffer, 0, 1);
    return buffer[0];
}
```

#### Decrypt

```csharp
public override void Decrypt (Xp3Entry entry, long offset, byte[] buffer, int pos, int count) {
    CxDecryptCore (entry, offset, buffer, pos, count);
}
```

#### CxDecryptCore

```csharp
protected void CxDecryptCore (Xp3Entry entry, long offset, byte[] buffer, int pos, int count) {
    uint key = entry.Hash;
    uint base_offset = GetBaseOffset (key);
    if (offset < base_offset)
    {
        int base_length = Math.Min ((int)(base_offset - offset), count);
        Decode (key, offset, buffer, pos, base_length);
        offset += base_length;
        pos += base_length;
        count -= base_length;
    }
    if (count > 0)
    {
        key = (key >> 16) ^ key;
        Decode (key, offset, buffer, pos, count);
    }
}
```

#### Decode

```csharp
void Decode (uint key, long offset, byte[] buffer, int pos, int count) {
    Tuple<uint, uint> ret = ExecuteXCode (key);
    uint key1 = ret.Item2 >> 16;
    uint key2 = ret.Item2 & 0xffff;
    byte key3 = (byte)(ret.Item1);
    if (key1 == key2)
        key2 += 1;
    if (0 == key3)
        key3 = 1;

    if ((key2 >= offset) && (key2 < offset + count))
        buffer[pos + key2 - offset] ^= (byte)(ret.Item1 >> 16);

    if ((key1 >= offset) && (key1 < offset + count))
        buffer[pos + key1 - offset] ^= (byte)(ret.Item1 >> 8);

    for (int i = 0; i < count; ++i)
        buffer[pos + i] ^= key3;
}
```

#### Encrypt

```csharp
public override void Encrypt (Xp3Entry entry, long offset, byte[] values, int pos, int count) {
    CxDecryptCore (entry, offset, values, pos, count);
}
```

#### ExecuteXCode

```csharp
protected Tuple<uint, uint> ExecuteXCode (uint hash) {
    uint seed = hash & 0x7f;
    if (null == m_program_list[seed])
    {
        m_program_list[seed] = GenerateProgram (seed);
    }
    hash >>= 7;
    uint ret1 = m_program_list[seed].Execute (hash);
    uint ret2 = m_program_list[seed].Execute (~hash);
    return new Tuple<uint, uint> (ret1, ret2);
}
```

#### GenerateProgram

```csharp
CxProgram GenerateProgram (uint seed) {
    var program = NewProgram (seed);
    for (int stage = 5; stage > 0; --stage)
    {
        if (EmitCode (program, stage))
            return program;

        program.Clear();
    }
    throw new CxProgramException ("Overly large CxEncryption bytecode");
}
```

#### NewProgram

```csharp
internal virtual CxProgram NewProgram (uint seed) {
    return new CxProgram (seed, ControlBlock);
}
```

#### EmitCode

```csharp
bool EmitCode (CxProgram program, int stage) {
    return program.EmitNop (5)
        && program.Emit (CxByteCode.MOV_EDI_ARG, 4)
        && EmitBody (program, stage)
        && program.EmitNop (5)
        && program.Emit (CxByteCode.RETN);
}
```

#### EmitBody

```csharp
bool EmitBody (CxProgram program, int stage) {
    if (1 == stage)
        return EmitProlog (program);

    if (!program.Emit (CxByteCode.PUSH_EBX))
        return false;

    if (0 != (program.GetRandom() & 1))
    {
        if (!EmitBody (program, stage - 1))
            return false;
    }
    else if (!EmitBody2 (program, stage - 1))
        return false;

    if (!program.Emit (CxByteCode.MOV_EBX_EAX, 2))
        return false;

    if (0 != (program.GetRandom() & 1))
    {
        if (!EmitBody (program, stage - 1))
            return false;
    }
    else if (!EmitBody2 (program, stage - 1))
        return false;

    return EmitOddBranch (program) && program.Emit (CxByteCode.POP_EBX);
}
```

#### EmitBody2

```csharp
bool EmitBody2 (CxProgram program, int stage) {
    if (1 == stage)
        return EmitProlog (program);

    bool rc = true;
    if (0 != (program.GetRandom() & 1))
        rc = EmitBody (program, stage - 1);
    else
        rc = EmitBody2 (program, stage - 1);

    return rc && EmitEvenBranch (program);
}
```

#### EmitProlog

```csharp
bool EmitProlog (CxProgram program) {
    bool rc = true;
    switch (PrologOrder[program.GetRandom() % 3])
    {
    case 2:

        rc =   program.EmitNop (5)
            && program.Emit (CxByteCode.MOV_EAX_IMMED, 2)
            && program.EmitUInt32 (program.GetRandom() & 0x3ff)
            && program.Emit (CxByteCode.MOV_EAX_INDIRECT, 0);
        break;
    case 1:
        rc = program.Emit (CxByteCode.MOV_EAX_EDI, 2);
        break;
    case 0:

        rc =   program.Emit (CxByteCode.MOV_EAX_IMMED)
            && program.EmitRandom();
        break;
    }
    return rc;
}
```

#### EmitEvenBranch

```csharp
bool EmitEvenBranch (CxProgram program) {
    bool rc = true;
    switch (EvenBranchOrder[program.GetRandom() & 7])
    {
    case 0:
        rc = program.Emit (CxByteCode.NOT_EAX, 2);
        break;
    case 1:
        rc = program.Emit (CxByteCode.DEC_EAX);
        break;
    case 2:
        rc = program.Emit (CxByteCode.NEG_EAX, 2);
        break;
    case 3:
        rc = program.Emit (CxByteCode.INC_EAX);
        break;
    case 4:
        rc =   program.EmitNop (5)
            && program.Emit (CxByteCode.AND_EAX_IMMED)
            && program.EmitUInt32 (0x3ff)
            && program.Emit (CxByteCode.MOV_EAX_INDIRECT, 3);
        break;
    case 5:
        rc =   program.Emit (CxByteCode.PUSH_EBX)
            && program.Emit (CxByteCode.MOV_EBX_EAX, 2)
            && program.Emit (CxByteCode.AND_EBX_IMMED, 2)
            && program.EmitUInt32 (0xaaaaaaaa)
            && program.Emit (CxByteCode.AND_EAX_IMMED)
            && program.EmitUInt32 (0x55555555)
            && program.Emit (CxByteCode.SHR_EBX_1, 2)
            && program.Emit (CxByteCode.SHL_EAX_1, 2)
            && program.Emit (CxByteCode.OR_EAX_EBX, 2)
            && program.Emit (CxByteCode.POP_EBX);
        break;
    case 6:
        rc =   program.Emit (CxByteCode.XOR_EAX_IMMED)
            && program.EmitRandom();
        break;
    case 7:
        if (0 != (program.GetRandom() & 1))
            rc = program.Emit (CxByteCode.ADD_EAX_IMMED);
        else
            rc = program.Emit (CxByteCode.SUB_EAX_IMMED);
        rc = rc && program.EmitRandom();
        break;
    }
    return rc;
}
```

#### EmitOddBranch

```csharp
bool EmitOddBranch (CxProgram program) {
    bool rc = true;
    switch (OddBranchOrder[program.GetRandom() % 6])
    {
    case 0:
        rc =   program.Emit (CxByteCode.PUSH_ECX)
            && program.Emit (CxByteCode.MOV_ECX_EBX, 2)
            && program.Emit (CxByteCode.AND_ECX_0F, 3)
            && program.Emit (CxByteCode.SHR_EAX_CL, 2)
            && program.Emit (CxByteCode.POP_ECX);
        break;
    case 1:
        rc =   program.Emit (CxByteCode.PUSH_ECX)
            && program.Emit (CxByteCode.MOV_ECX_EBX, 2)
            && program.Emit (CxByteCode.AND_ECX_0F, 3)
            && program.Emit (CxByteCode.SHL_EAX_CL, 2)
            && program.Emit (CxByteCode.POP_ECX);
        break;
    case 2:
        rc = program.Emit (CxByteCode.ADD_EAX_EBX, 2);
        break;
    case 3:
        rc =   program.Emit (CxByteCode.NEG_EAX, 2)
            && program.Emit (CxByteCode.ADD_EAX_EBX, 2);
        break;
    case 4:
        rc = program.Emit (CxByteCode.IMUL_EAX_EBX, 3);
        break;
    case 5:
        rc = program.Emit (CxByteCode.SUB_EAX_EBX, 2);
        break;
    }
    return rc;
}
```

### GameRes.Formats.KiriKiri.CxProgram

#### 状态与常量

```csharp
public const int    LengthLimit = 0x80 ;

private List<uint>  m_code = new List<uint> (LengthLimit) ;

private uint[]      m_ControlBlock ;

private int         m_length ;

protected uint      m_seed ;
```

#### CxProgram

```csharp
public CxProgram (uint seed, uint[] control_block) {
    m_seed = seed;
    m_length = 0;
    m_ControlBlock = control_block;
}
```

#### Execute

```csharp
public uint Execute (uint hash) {
    var context = new Context();
    using (var iterator = m_code.GetEnumerator())
    {
        uint immed = 0;
        while (iterator.MoveNext())
        {
            var bytecode = (CxByteCode)iterator.Current;
            if (CxByteCode.IMMED == (bytecode & CxByteCode.IMMED))
            {
                if (!iterator.MoveNext())
                    throw new CxProgramException ("Incomplete IMMED bytecode in CxEncryption program");
                immed = iterator.Current;
            }
            switch (bytecode)
            {
            case CxByteCode.NOP: break;
            case CxByteCode.IMMED: break;
            case CxByteCode.MOV_EDI_ARG:    context.edi = hash; break;
            case CxByteCode.PUSH_EBX:       context.stack.Push (context.ebx); break;
            case CxByteCode.POP_EBX:        context.ebx = context.stack.Pop(); break;
            case CxByteCode.PUSH_ECX:       context.stack.Push (context.ecx); break;
            case CxByteCode.POP_ECX:        context.ecx = context.stack.Pop(); break;
            case CxByteCode.MOV_EBX_EAX:    context.ebx = context.eax; break;
            case CxByteCode.MOV_EAX_EDI:    context.eax = context.edi; break;
            case CxByteCode.MOV_ECX_EBX:    context.ecx = context.ebx; break;
            case CxByteCode.MOV_EAX_EBX:    context.eax = context.ebx; break;

            case CxByteCode.AND_ECX_0F:     context.ecx &= 0x0f; break;
            case CxByteCode.SHR_EBX_1:      context.ebx >>= 1; break;
            case CxByteCode.SHL_EAX_1:      context.eax <<= 1; break;
            case CxByteCode.SHR_EAX_CL:     context.eax >>= (int)context.ecx; break;
            case CxByteCode.SHL_EAX_CL:     context.eax <<= (int)context.ecx; break;
            case CxByteCode.OR_EAX_EBX:     context.eax |= context.ebx; break;
            case CxByteCode.NOT_EAX:        context.eax = ~context.eax; break;
            case CxByteCode.NEG_EAX:        context.eax = (uint)-context.eax; break;
            case CxByteCode.DEC_EAX:        context.eax--; break;
            case CxByteCode.INC_EAX:        context.eax++; break;

            case CxByteCode.ADD_EAX_EBX:    context.eax += context.ebx; break;
            case CxByteCode.SUB_EAX_EBX:    context.eax -= context.ebx; break;
            case CxByteCode.IMUL_EAX_EBX:   context.eax *= context.ebx; break;

            case CxByteCode.ADD_EAX_IMMED:  context.eax += immed; break;
            case CxByteCode.SUB_EAX_IMMED:  context.eax -= immed; break;
            case CxByteCode.AND_EBX_IMMED:  context.ebx &= immed; break;
            case CxByteCode.AND_EAX_IMMED:  context.eax &= immed; break;
            case CxByteCode.XOR_EAX_IMMED:  context.eax ^= immed; break;
            case CxByteCode.MOV_EAX_IMMED:  context.eax = immed; break;
            case CxByteCode.MOV_EAX_INDIRECT:
                if (context.eax >= m_ControlBlock.Length)
                    throw new CxProgramException ("Index out of bounds in CxEncryption program");
                context.eax = ~m_ControlBlock[context.eax];
                break;

            case CxByteCode.RETN:
                if (context.stack.Count > 0)
                    throw new CxProgramException ("Imbalanced stack in CxEncryption program");
                return context.eax;

            default:
                throw new CxProgramException ("Invalid bytecode in CxEncryption program");
            }
        }
    }
    throw new CxProgramException ("CxEncryption program without RETN bytecode");
}
```

#### Clear

```csharp
public void Clear () {
    m_length = 0;
    m_code.Clear();
}
```

#### EmitNop

```csharp
public bool EmitNop (int count) {
    if (m_length + count > LengthLimit)
        return false;
    m_length += count;
    return true;
}
```

#### Emit

```csharp
public bool Emit (CxByteCode code, int length = 1) {
    if (m_length + length > LengthLimit)
        return false;
    m_length += length;
    m_code.Add ((uint)code);
    return true;
}
```

#### EmitUInt32

```csharp
public bool EmitUInt32 (uint x) {
    if (m_length + 4 > LengthLimit)
        return false;
    m_length += 4;
    m_code.Add (x);
    return true;
}
```

#### EmitRandom

```csharp
public bool EmitRandom () {
    return EmitUInt32 (GetRandom());
}
```

#### GetRandom

```csharp
public virtual uint GetRandom () {
    uint seed = m_seed;
    m_seed = 1103515245 * seed + 12345;
    return m_seed ^ (seed << 16) ^ (seed >> 16);
}
```

### GameRes.Formats.KiriKiri.CxProgram.Context

#### 状态与常量

```csharp
public uint eax ;

public uint ebx ;

public uint ecx ;

public uint edi ;

public Stack<uint> stack = new Stack<uint>() ;
```

## 配套算法与外部条件

- [ArcFormats/KiriKiri/ArcXP3.cs](ArcXP3.md)：本页引用的随包算法资料。
- [ArcFormats/KiriKiri/CryptAlgorithms.cs](CryptAlgorithms.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/KiriKiri/KiriKiriCx.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
