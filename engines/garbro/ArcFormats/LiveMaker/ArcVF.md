# LiveMaker / ArcVF：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/vf` / `GameRes.Formats.LiveMaker.VffOpener` | `dat`, `exe` | `76666600`, `4d5a9000` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `VffOpener.TryOpen` | `uint signature = index_file.View.ReadUInt32 (0);` |
| `VffOpener.TryOpen` | `signature = index_file.View.ReadUInt32 (base_offset);` |
| `VffOpener.TryOpen` | `signature = index_file.View.ReadUInt32 (0);` |
| `VffOpener.TryOpen` | `int count = index_file.View.ReadInt32 (base_offset+6);` |
| `VffOpener.ReadIndex` | `uint name_length = file.View.ReadUInt32 (index_offset);` |
| `VffOpener.ReadIndex` | `long offset = base_offset + (file.View.ReadInt64 (index_offset) ^ (int)rnd.GetRand32());` |
| `VffOpener.ReadIndex` | `long next_offset = base_offset + (file.View.ReadInt64 (index_offset) ^ (int)rnd.GetRand32());` |
| `VffOpener.ReadIndex` | `byte flags = file.View.ReadByte (index_offset++);` |
| `VffOpener.ReshuffleStream` | `int chunk_size = header.ToInt32 (0);` |
| `VffOpener.ReshuffleStream` | `uint seed = header.ToUInt32 (4) ^ 0xF8EAu;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.LiveMaker.VffOpener

继承/接口：`ArchiveFormat`。

#### VffOpener

```csharp
public VffOpener () {
    Extensions = new string[] { "dat", "exe" };
    Signatures = new uint[] { 0x666676, 0x00905A4D, 0 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint base_offset = 0;
    ArcView index_file = file;
    try
    {

        uint signature = index_file.View.ReadUInt32 (0);
        if (file.Name.HasExtension (".exe")
            && (0x5A4D == (signature & 0xFFFF)))
        {
            base_offset = SkipExeData (index_file);
            if (base_offset >= file.MaxOffset)
                return null;
            signature = index_file.View.ReadUInt32 (base_offset);
        }
        else if (!file.Name.HasExtension (".dat"))
        {
            return null;
        }
        else if (0x666676 != signature)
        {
            var ext_filename = Path.ChangeExtension (file.Name, ".ext");
            if (!VFS.FileExists (ext_filename))
                return null;
            index_file = VFS.OpenView (ext_filename);
            signature = index_file.View.ReadUInt32 (0);
        }
        if (0x666676 != signature)
            return null;
        int count = index_file.View.ReadInt32 (base_offset+6);
        if (!IsSaneCount (count))
            return null;

        var dir = ReadIndex (index_file, base_offset, count);
        if (null == dir)
            return null;
        long max_offset = file.MaxOffset;
        var parts = new List<ArcView>();
        try
        {
            for (int i = 1; i < 100; ++i)
            {
                var ext = string.Format (".{0:D3}", i);
                var part_filename = Path.ChangeExtension (file.Name, ext);
                if (!VFS.FileExists (part_filename))
                    break;
                var arc_file = VFS.OpenView (part_filename);
                max_offset += arc_file.MaxOffset;
                parts.Add (arc_file);
            }
        }
        catch
        {
            foreach (var part in parts)
                part.Dispose();
            throw;
        }
        if (0 == parts.Count)
            return new ArcFile (file, this, dir);
        return new MultiFileArchive (file, this, dir, parts);
    }
    finally
    {
        if (index_file != file)
            index_file.Dispose();
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var vff = arc as MultiFileArchive;
    Stream input = null;
    if (vff != null)
        input = vff.OpenStream (entry);
    else
        input = arc.File.CreateStream (entry.Offset, entry.Size);

    var pent = entry as VfEntry;
    if (null == pent)
        return input;
    if (pent.IsScrambled)
    {
        byte[] data;
        using (input)
        {
            if (entry.Size <= 8)
                return Stream.Null;
            data = ReshuffleStream (input);
        }
        input = new BinMemoryStream (data, entry.Name);
    }
    if (pent.IsPacked)
        input = new ZLibStream (input, CompressionMode.Decompress);
    return input;
}
```

#### ReadIndex

```csharp
List<Entry> ReadIndex (ArcView file, uint base_offset, int count) {
    uint index_offset = base_offset+0xA;
    var name_buffer = new byte[0x100];
    var rnd = new TpRandom (0x75D6EE39u);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint name_length = file.View.ReadUInt32 (index_offset);
        index_offset += 4;
        if (0 == name_length || name_length > name_buffer.Length)
            return null;
        if (name_length != file.View.Read (index_offset, name_buffer, 0, name_length))
            return null;
        index_offset += name_length;

        var name = DecryptName (name_buffer, (int)name_length, rnd);
        dir.Add (Create<VfEntry> (name));
    }
    rnd.Reset();
    long offset = base_offset + (file.View.ReadInt64 (index_offset) ^ (int)rnd.GetRand32());
    foreach (var entry in dir)
    {
        index_offset += 8;
        long next_offset = base_offset + (file.View.ReadInt64 (index_offset) ^ (int)rnd.GetRand32());
        entry.Offset = offset;
        entry.Size = (uint)(next_offset - offset);
        offset = next_offset;
    }
    index_offset += 8;
    foreach (VfEntry entry in dir)
    {
        byte flags = file.View.ReadByte (index_offset++);
        entry.IsPacked = 0 == flags || 3 == flags;
        entry.IsScrambled = 2 == flags || 3 == flags;
    }
    return dir;
}
```

#### DecryptName

```csharp
string DecryptName (byte[] name_buf, int name_length, TpRandom key) {
    for (int i = 0; i < name_length; ++i)
    {
        name_buf[i] ^= (byte)key.GetRand32();
    }
    return Encodings.cp932.GetString (name_buf, 0, name_length);
}
```

#### SkipExeData

```csharp
uint SkipExeData (ArcView file) {
    var exe = new ExeFile (file);
    return (uint)exe.Overlay.Offset;
}
```

#### ReshuffleStream

```csharp
byte[] ReshuffleStream (Stream input) {
    var header = new byte[8];
    input.Read (header, 0, 8);
    int chunk_size = header.ToInt32 (0);
    uint seed = header.ToUInt32 (4) ^ 0xF8EAu;
    int input_length = (int)input.Length - 8;
    var output = new byte[input_length];
    int count = (input_length - 1) / chunk_size + 1;
    int dst = 0;
    foreach (int i in RandomSequence (count, seed))
    {
        int position = i * chunk_size;
        input.Position = 8 + position;
        int length = Math.Min (chunk_size, input_length - position);
        input.Read (output, dst, length);
        dst += length;
    }
    return output;
}
```

#### RandomSequence

```csharp
static IEnumerable<int> RandomSequence (int count, uint seed) {
    var tp = new TpScramble (seed);
    var order = Enumerable.Range (0, count).ToList<int>();
    var seq = new int[order.Count];
    for (int i = 0; order.Count > 1; ++i)
    {
        int n = tp.GetInt32 (0, order.Count - 2);
        seq[order[n]] = i;
        order.RemoveAt (n);
    }
    seq[order[0]] = count - 1;
    return seq;
}
```

### GameRes.Formats.LiveMaker.VfEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public bool IsScrambled ;
```

### GameRes.Formats.LiveMaker.TpRandom

#### 状态与常量

```csharp
uint    m_seed ;

uint    m_current ;
```

#### TpRandom

```csharp
public TpRandom (uint seed) {
    m_seed = seed;
    m_current = 0;
}
```

#### GetRand32

```csharp
public uint GetRand32 () {
    m_current += m_current << 2;
    m_current += m_seed;
    return m_current;
}
```

#### Reset

```csharp
public void Reset () {
    m_current = 0;
}
```

### GameRes.Formats.LiveMaker.TpScramble

#### 状态与常量

```csharp
uint[]  m_state = new uint[5] ;

const uint FactorA = 2111111111 ;

const uint FactorB = 1492 ;

const uint FactorC = 1776 ;

const uint FactorD = 5115 ;
```

#### TpScramble

```csharp
public TpScramble (uint seed) {
    Init (seed);
}
```

#### Init

```csharp
public void Init (uint seed) {
    uint hash = seed != 0 ? seed : 0xFFFFFFFFu;
    for (int i = 0; i < 5; ++i)
    {
        hash ^= hash << 13;
        hash ^= hash >> 17;
        hash ^= hash << 5;
        m_state[i] = hash;
    }
    for (int i = 0; i < 19; ++i)
    {
        GetUInt32();
    }
}
```

#### GetInt32

```csharp
public int GetInt32 (int first, int last) {
    var num = GetDouble();
    return (int)(first + (long)(num * (last - first + 1)));
}
```

#### GetDouble

```csharp
double GetDouble () {
    return (double)GetUInt32() / 0x100000000L;
}
```

#### GetUInt32

```csharp
uint GetUInt32 () {
    ulong v = FactorA * (ulong)m_state[3]
            + FactorB * (ulong)m_state[2]
            + FactorC * (ulong)m_state[1]
            + FactorD * (ulong)m_state[0] + m_state[4];
    m_state[3] = m_state[2];
    m_state[2] = m_state[1];
    m_state[1] = m_state[0];
    m_state[4] = (uint)(v >> 32);
    return m_state[0] = (uint)v;
}
```

## 配套算法与外部条件

- [ArcFormats/ExeFile.cs](../ExeFile.md)：本页引用的随包算法资料。
- [ArcFormats/MultiFileArchive.cs](../MultiFileArchive.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/LiveMaker/ArcVF.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
