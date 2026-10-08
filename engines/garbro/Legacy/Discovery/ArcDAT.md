# Discovery / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/DISCOVERY` / `GameRes.Formats.Discovery.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (file.MaxOffset-4);` |
| `DatOpener.ReadBDataIndex` | `var index = file.View.ReadBytes (file.MaxOffset - 4 - index_size, (uint)index_size);` |
| `DatOpener.ReadBDataIndex` | `entry.Size         = index.ToUInt32 (index_offset+4);` |
| `DatOpener.ReadBDataIndex` | `entry.UnpackedSize = index.ToUInt32 (index_offset+8);` |
| `DatOpener.ReadBDataIndex` | `entry.Offset       = index.ToUInt32 (index_offset+0xC);` |
| `DatOpener.ReadBDataIndex` | `entry.Width  = index.ToUInt32 (index_offset+0x10);` |
| `DatOpener.ReadBDataIndex` | `entry.Height = index.ToUInt32 (index_offset+0x14);` |
| `DatOpener.ReadBDataIndex` | `entry.Extra  = index.ToUInt16 (index_offset+0x28);` |
| `DatOpener.ReadBDataIndex` | `entry.Colors = index.ToUInt16 (index_offset+0x2A);` |
| `DatOpener.ReadEDataIndex` | `var index = file.View.ReadBytes (file.MaxOffset - 4 - index_size, (uint)index_size);` |
| `DatOpener.ReadEDataIndex` | `entry.BodySize       = index.ToUInt32 (index_offset+4);` |
| `DatOpener.ReadEDataIndex` | `entry.BodyUnpacked   = index.ToUInt32 (index_offset+8);` |
| `DatOpener.ReadEDataIndex` | `entry.BodyOffset     = index.ToUInt32 (index_offset+0xC);` |
| `DatOpener.ReadEDataIndex` | `entry.HeaderSize     = index.ToUInt32 (index_offset+0x10);` |
| `DatOpener.ReadEDataIndex` | `entry.HeaderUnpacked = index.ToUInt32 (index_offset+0x14);` |
| `DatOpener.ReadEDataIndex` | `entry.Offset         = index.ToUInt32 (index_offset+0x18);` |
| `DatOpener.ReadVDataIndex` | `var index = file.View.ReadBytes (file.MaxOffset - 4 - index_size, (uint)index_size);` |
| `DatOpener.ReadVDataIndex` | `entry.Size   = index.ToUInt32 (index_offset+8);` |
| `DatOpener.ReadVDataIndex` | `entry.Offset = index.ToUInt32 (index_offset+0xC);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Discovery.BDataEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint     Width ;

public uint     Height ;

public int      BPP ;

public int      Colors ;

public int      Extra ;

public bool     IsMask ;
```

### GameRes.Formats.Discovery.EDataEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint     HeaderSize ;

public uint     HeaderUnpacked ;

public uint     BodyOffset ;

public uint     BodySize ;

public uint     BodyUnpacked ;
```

### GameRes.Formats.Discovery.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    int count = file.View.ReadInt32 (file.MaxOffset-4);
    if (!IsSaneCount (count))
        return null;
    var arc_name = Path.GetFileName (file.Name);
    List<Entry> dir = null;
    if (arc_name.StartsWith ("BData", StringComparison.OrdinalIgnoreCase))
        dir = ReadBDataIndex (file, count);
    else if (arc_name.StartsWith ("EData", StringComparison.OrdinalIgnoreCase))
        dir = ReadEDataIndex (file, count);
    else if (arc_name.StartsWith ("VData", StringComparison.OrdinalIgnoreCase))
        dir = ReadVDataIndex (file, count);
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### ReadBDataIndex

```csharp
List<Entry> ReadBDataIndex (ArcView file, int count) {
    int entry_size = 0x3C;
    int index_size = count * entry_size;
    if (index_size+4 >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (file.MaxOffset - 4 - index_size, (uint)index_size);
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        Decrypt (index, index_offset, entry_size);
        int name_length = index[index_offset];
        if (0 == name_length || name_length > entry_size - 0x18)
            return null;
        var name = Encodings.cp932.GetString (index, index_offset+0x18, name_length);
        var entry = FormatCatalog.Instance.Create<BDataEntry> (name);
        entry.Size         = index.ToUInt32 (index_offset+4);
        entry.UnpackedSize = index.ToUInt32 (index_offset+8);
        entry.IsPacked     = entry.Size != entry.UnpackedSize;
        entry.Offset       = index.ToUInt32 (index_offset+0xC);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.Width  = index.ToUInt32 (index_offset+0x10);
        entry.Height = index.ToUInt32 (index_offset+0x14);
        entry.BPP    = index[index_offset+1];
        entry.IsMask = index[index_offset+2] == 1;
        entry.Extra  = index.ToUInt16 (index_offset+0x28);
        entry.Colors = index.ToUInt16 (index_offset+0x2A);
        dir.Add (entry);
        index_offset += entry_size;
    }
    return dir;
}
```

#### ReadEDataIndex

```csharp
List<Entry> ReadEDataIndex (ArcView file, int count) {
    int entry_size = 0x2C;
    int index_size = count * entry_size;
    if (index_size+4 >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (file.MaxOffset - 4 - index_size, (uint)index_size);
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        Decrypt (index, index_offset, entry_size);
        int name_length = index[index_offset];
        if (0 == name_length || name_length > entry_size - 0x1C)
            return null;
        var name = Encodings.cp932.GetString (index, index_offset+0x1C, name_length);
        var entry = FormatCatalog.Instance.Create<EDataEntry> (name);
        entry.BodySize       = index.ToUInt32 (index_offset+4);
        entry.BodyUnpacked   = index.ToUInt32 (index_offset+8);
        entry.BodyOffset     = index.ToUInt32 (index_offset+0xC);
        entry.HeaderSize     = index.ToUInt32 (index_offset+0x10);
        entry.HeaderUnpacked = index.ToUInt32 (index_offset+0x14);
        entry.Offset         = index.ToUInt32 (index_offset+0x18);
        entry.Size = entry.HeaderSize + entry.BodySize;
        entry.UnpackedSize = entry.HeaderUnpacked + entry.BodyUnpacked;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        entry.IsPacked = true;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return dir;
}
```

#### ReadVDataIndex

```csharp
List<Entry> ReadVDataIndex (ArcView file, int count) {
    int entry_size = 0x20;
    int index_size = count * entry_size;
    if (index_size+4 >= file.MaxOffset)
        return null;
    var index = file.View.ReadBytes (file.MaxOffset - 4 - index_size, (uint)index_size);
    for (int i = 0; i < index.Length; ++i)
        index[i] ^= 0xDE;
    int index_offset = 0;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int name_length = index[index_offset];
        if (0 == name_length || name_length > entry_size - 0x10)
            return null;
        var name = Encodings.cp932.GetString (index, index_offset+0x10, name_length);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Size   = index.ToUInt32 (index_offset+8);
        entry.Offset = index.ToUInt32 (index_offset+0xC);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += entry_size;
    }
    return dir;
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var eent = entry as EDataEntry;
    if (null == eent || !eent.IsPacked)
        return base.OpenEntry (arc, entry);
    var header = new byte[eent.HeaderUnpacked];
    using (var input = arc.File.CreateStream (eent.Offset, eent.HeaderSize))
    using (var lzss = new LzssStream (input))
        lzss.Read (header, 0, header.Length);
    Stream body = arc.File.CreateStream (eent.BodyOffset, eent.BodySize);
    body = new LzssStream (body);
    return new PrefixStream (header, body);
}
```

#### Decrypt

```csharp
void Decrypt (byte[] data, int pos, int length) {
    Descramble32 (data, pos, length, 13);
    Descramble8 (data, pos, length, 7);
    for (int i = 0; i < length; ++i)
        data[pos+i] ^= 0xD6;
}
```

#### Descramble32

```csharp
unsafe void Descramble32 (byte[] data, int pos, int length, int seed) {
    length /= 4;
    fixed (byte* data8 = &data[pos])
    {
        uint* data32 = (uint*)data8;
        for (int i = 0; i < length; ++i)
        {
            int s = 0;
            uint x = ~(data32[i] & 1) & data32[i];
            int shift = 0;
            for (int j = 0; j < 31; ++j)
            {
                shift = s - seed;
                if (shift < 0)
                    shift += ((31 - shift) >> 5) << 5;
                uint bit = x & (1u << shift);
                uint a = ~bit & x;
                uint b;
                if (shift <= s)
                    b = bit << (s - shift);
                else
                    b = bit >> (shift - s);
                x = b | a;
                s = shift;
            }
            data32[i] = x | ((data32[i] & 1) << shift);
        }
    }
}
```

#### Descramble8

```csharp
void Descramble8 (byte[] data, int pos, int length, int seed) {
    byte first = data[pos];
    int x = 0;
    int i = 0;
    for (int count = length - 1; count > 0; --count)
    {
        i = x - seed;
        while (i < 0)
            i += length;
        data[pos+x] = data[pos+i];
        x = i;
    }
    data[pos+i] = first;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../../ArcFormats/LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Discovery/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
