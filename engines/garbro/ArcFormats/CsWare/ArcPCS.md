# CsWare / ArcPCS：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PCS` / `GameRes.Formats.CsWare.PcsOpener` | `pcs` | `50434353` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PcsOpener.TryOpen` | `int version = file.View.ReadUInt16 (4);` |
| `PcsOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `PcsOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (12);` |
| `PcsOpener.TryOpen` | `var index = file.View.ReadBytes (0x10, index_size);` |
| `PcsOpener.TryOpen` | `index = ShuffleBlocks (index, file.View.ReadUInt16 (6));` |
| `PcsOpener.TryOpen` | `name_length = LittleEndian.ToInt32 (index, index_offset);` |
| `PcsOpener.TryOpen` | `entry.Offset = LittleEndian.ToUInt32 (index, index_offset) + data_offset;` |
| `PcsOpener.TryOpen` | `entry.Size   = LittleEndian.ToUInt32 (index, index_offset+4);` |
| `PcsOpener.OpenEntry` | `var header = arc.File.View.ReadBytes (entry.Offset, header_size);` |
| `PcsOpener.ComputeHash` | `return BigEndian.ToUInt32 (hash, 0);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CsWare.PcsEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte Key ;

public uint NameHash ;
```

### GameRes.Formats.CsWare.PcsArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly int Version ;
```

#### PcsArchive

```csharp
public PcsArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int version)
    : base (arc, impl, dir) {
    Version = version;
}
```

### GameRes.Formats.CsWare.PcsOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Lazy<HashAlgorithm> SHA1 = new Lazy<HashAlgorithm> (() => System.Security.Cryptography.SHA1.Create()) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadUInt16 (4);
    if (version < 1 || version > 6)
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;
    uint data_offset = file.View.ReadUInt32 (12);
    uint index_size = data_offset - 0x10;
    var index = file.View.ReadBytes (0x10, index_size);
    if (6 == version)
    {
        index = ShuffleBlocks (index, file.View.ReadUInt16 (6));
    }
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_length;
        if (version > 1)
        {
            name_length = LittleEndian.ToInt32 (index, index_offset);
            if (0 == name_length)
                break;
            if (name_length > index_size)
                return null;
            index_offset += 5 + name_length;
        }
        name_length = LittleEndian.ToInt32 (index, index_offset);
        if (0 == name_length)
            break;
        if (name_length > index_size)
            return null;
        index_offset += 5;
        byte checksum;
        var name = DecryptName (index, index_offset, name_length, out checksum);
        Entry entry;
        if (version >= 4)
        {
            var pcs_entry = FormatCatalog.Instance.Create<PcsEntry> (name);
            entry = pcs_entry;
            pcs_entry.Key = checksum;
            if (6 == version)
                pcs_entry.NameHash = ComputeHash (index, index_offset, name_length-1);
            index_offset += name_length;
            int c = -1 - checksum;
            for (int j = 0; j < 4; ++j)
            {
                byte key = (byte)((checksum + (17 << j)) & 0x33);
                index[index_offset+j]   = (byte)(c + key - index[index_offset+j]);
                index[index_offset+j+4] = (byte)(c + key - index[index_offset+j+4]);
            }
        }
        else
        {
            index_offset += name_length;
            entry = FormatCatalog.Instance.Create<Entry> (name);
        }
        if (index_offset > data_offset)
            return null;
        entry.Offset = LittleEndian.ToUInt32 (index, index_offset) + data_offset;
        entry.Size   = LittleEndian.ToUInt32 (index, index_offset+4);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x10;
    }
    if (0 == dir.Count)
        return null;
    return new PcsArchive (file, this, dir, version);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PcsEntry;
    var parc = arc as PcsArchive;
    if (null == pent || null == parc)
        return base.OpenEntry (arc, entry);
    uint header_size = Math.Min (entry.Size, 512u);
    var header = arc.File.View.ReadBytes (entry.Offset, header_size);
    if (6 == parc.Version)
    {
        header = ShuffleBlocks (header, pent.NameHash);
    }
    for (int i = 0; i < header.Length; ++i)
    {
        header[i] = (byte)(pent.Key - header[i] - 1);
    }
    if (header_size == entry.Size)
        return new BinMemoryStream (header, entry.Name);
    var rest = arc.File.CreateStream (entry.Offset+512, entry.Size-512);
    return new PrefixStream (header, rest);
}
```

#### DecryptName

```csharp
string DecryptName (byte[] name_buffer, int offset, int length, out byte checksum) {
    int count;
    checksum = 0;
    for (count = 0; count < length; ++count)
    {
        if (0 == name_buffer[offset+count])
            break;
        name_buffer[offset+count] = Binary.RotByteL (name_buffer[offset+count], 4);
        checksum += name_buffer[offset+count];
    }
    return Encodings.cp932.GetString (name_buffer, offset, count);
}
```

#### ShuffleBlocks

```csharp
byte[] ShuffleBlocks (byte[] input, uint key) {
    int block_size = input.Length >> 5;
    var output = new byte[input.Length];
    var twister = new MersenneTwister (key);
    int copied_sections = 0;
    for (int i = 0; i < 0x20; ++i)
    {
        int j = (int)(twister.Rand() & 0x1F);
        while (0 != (copied_sections & (1 << j)))
            j = (j + 1) & 0x1F;
        copied_sections |= 1 << j;
        Buffer.BlockCopy (input, j * block_size, output, i * block_size, block_size);
    }
    int shuffled = block_size << 5;
    if (shuffled != input.Length)
        Buffer.BlockCopy (input, shuffled, output, shuffled, input.Length-shuffled);
    return output;
}
```

#### ComputeHash

```csharp
uint ComputeHash (byte[] data, int offset, int length) {
    var hash = SHA1.Value.ComputeHash (data, offset, length);
    return BigEndian.ToUInt32 (hash, 0);
}
```

## 配套算法与外部条件

- [ArcFormats/MersenneTwister.cs](../MersenneTwister.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/CsWare/ArcPCS.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
