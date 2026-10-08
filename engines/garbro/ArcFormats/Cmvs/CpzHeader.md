# Cmvs / CpzHeader：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `CpzHeader.Parse` | `var cpz = new CpzHeader { Version = file.View.ReadByte (3) - '0' };` |
| `CpzHeader.Parse` | `header = file.View.ReadBytes (0, 0x40);` |
| `CpzHeader.Parse` | `cpz.Checksum = header.ToUInt32 (0x3C);` |
| `CpzHeader.Parse` | `header = file.View.ReadBytes (0, 0x48);` |
| `CpzHeader.Parse` | `cpz.Checksum = header.ToUInt32 (0x44);` |
| `CpzHeader.ParseV5` | `DirCount        = -0x1C5AC27 ^ LittleEndian.ToInt32 (header, 4);` |
| `CpzHeader.ParseV5` | `DirEntriesSize  = 0x37F298E7 ^ LittleEndian.ToInt32 (header, 8);` |
| `CpzHeader.ParseV5` | `FileEntriesSize = 0x7A6F3A2C ^ LittleEndian.ToInt32 (header, 0x0C);` |
| `CpzHeader.ParseV5` | `MasterKey       = 0xAE7D39BF ^ LittleEndian.ToUInt32 (header, 0x30);` |
| `CpzHeader.ParseV5` | `IsEncrypted     = 0 != (0xFB73A955 ^ LittleEndian.ToUInt32 (header, 0x34));` |
| `CpzHeader.ParseV5` | `CmvsMd5[0] = 0x43DE7C19 ^ LittleEndian.ToUInt32 (header, 0x20);` |
| `CpzHeader.ParseV5` | `CmvsMd5[1] = 0xCC65F415 ^ LittleEndian.ToUInt32 (header, 0x24);` |
| `CpzHeader.ParseV5` | `CmvsMd5[2] = 0xD016A93C ^ LittleEndian.ToUInt32 (header, 0x28);` |
| `CpzHeader.ParseV5` | `CmvsMd5[3] = 0x97A3BA9A ^ LittleEndian.ToUInt32 (header, 0x2C);` |
| `CpzHeader.ParseV6` | `uint entry_key  = 0x37ACF832 ^ LittleEndian.ToUInt32 (header, 0x38);` |
| `CpzHeader.ParseV6` | `DirCount        = -0x1C5AC26 ^ LittleEndian.ToInt32 (header, 4);` |
| `CpzHeader.ParseV6` | `DirEntriesSize  = 0x37F298E8 ^ LittleEndian.ToInt32 (header, 8);` |
| `CpzHeader.ParseV6` | `FileEntriesSize = 0x7A6F3A2D ^ LittleEndian.ToInt32 (header, 0x0C);` |
| `CpzHeader.ParseV6` | `MasterKey       = 0xAE7D39B7 ^ LittleEndian.ToUInt32 (header, 0x30);` |
| `CpzHeader.ParseV6` | `IsEncrypted     = 0 != (0xFB73A956 ^ LittleEndian.ToUInt32 (header, 0x34));` |
| `CpzHeader.ParseV6` | `CmvsMd5[0] = 0x43DE7C1A ^ LittleEndian.ToUInt32 (header, 0x20);` |
| `CpzHeader.ParseV6` | `CmvsMd5[1] = 0xCC65F416 ^ LittleEndian.ToUInt32 (header, 0x24);` |
| `CpzHeader.ParseV6` | `CmvsMd5[2] = 0xD016A93D ^ LittleEndian.ToUInt32 (header, 0x28);` |
| `CpzHeader.ParseV6` | `CmvsMd5[3] = 0x97A3BA9B ^ LittleEndian.ToUInt32 (header, 0x2C);` |
| `CpzHeader.ParseV7` | `var index_key_size = LittleEndian.ToInt32 (header, 0x40);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Purple.CpzHeader

#### 状态与常量

```csharp
public int      Version ;

public int      DirCount ;

public int      DirEntriesSize ;

public int      FileEntriesSize ;

public uint[]   CmvsMd5 = new uint[4] ;

public uint     MasterKey ;

public bool     IsEncrypted ;

public uint     EntryKey ;

public int      IndexKeySize ;

public uint     Checksum ;

public uint     InitChecksum = 0x923A564Cu ;

public uint     IndexOffset ;

public uint     IndexSize ;

public IEnumerable<byte> IndexMd5 ;

public int      EntryNameOffset ;

public bool IsLongSize { get { return Version > 6; } }
```

#### Parse

```csharp
public static CpzHeader Parse (ArcView file) {
    var cpz = new CpzHeader { Version = file.View.ReadByte (3) - '0' };
    int checksum_length;
    byte[] header;
    if (cpz.Version < 7)
    {
        header = file.View.ReadBytes (0, 0x40);
        if (cpz.Version < 6)
            cpz.ParseV5 (header);
        else
            cpz.ParseV6 (header);
        cpz.IndexOffset = 0x40;
        cpz.IndexSize = (uint)(cpz.DirEntriesSize + cpz.FileEntriesSize);
        cpz.Checksum = header.ToUInt32 (0x3C);
        checksum_length = 0x3C;
    }
    else
    {
        header = file.View.ReadBytes (0, 0x48);
        cpz.ParseV7 (header);
        cpz.IndexOffset = 0x48;
        cpz.IndexSize = (uint)(cpz.DirEntriesSize + cpz.FileEntriesSize + cpz.IndexKeySize);
        cpz.Checksum = header.ToUInt32 (0x44);
        checksum_length = 0x40;
    }
    if (cpz.Checksum != CheckSum (header, 0, checksum_length, cpz.InitChecksum))
        return null;

    cpz.IndexMd5 = header.Skip (0x10).Take (0x10).ToArray();
    return cpz;
}
```

#### ParseV5

```csharp
private void ParseV5 (byte[] header) {
    DirCount        = -0x1C5AC27 ^ LittleEndian.ToInt32 (header, 4);
    DirEntriesSize  = 0x37F298E7 ^ LittleEndian.ToInt32 (header, 8);
    FileEntriesSize = 0x7A6F3A2C ^ LittleEndian.ToInt32 (header, 0x0C);
    MasterKey       = 0xAE7D39BF ^ LittleEndian.ToUInt32 (header, 0x30);
    IsEncrypted     = 0 != (0xFB73A955 ^ LittleEndian.ToUInt32 (header, 0x34));
    EntryKey        = 0;
    EntryNameOffset = 0x18;
    CmvsMd5[0] = 0x43DE7C19 ^ LittleEndian.ToUInt32 (header, 0x20);
    CmvsMd5[1] = 0xCC65F415 ^ LittleEndian.ToUInt32 (header, 0x24);
    CmvsMd5[2] = 0xD016A93C ^ LittleEndian.ToUInt32 (header, 0x28);
    CmvsMd5[3] = 0x97A3BA9A ^ LittleEndian.ToUInt32 (header, 0x2C);
}
```

#### ParseV6

```csharp
private void ParseV6 (byte[] header) {
    uint entry_key  = 0x37ACF832 ^ LittleEndian.ToUInt32 (header, 0x38);
    DirCount        = -0x1C5AC26 ^ LittleEndian.ToInt32 (header, 4);
    DirEntriesSize  = 0x37F298E8 ^ LittleEndian.ToInt32 (header, 8);
    FileEntriesSize = 0x7A6F3A2D ^ LittleEndian.ToInt32 (header, 0x0C);
    MasterKey       = 0xAE7D39B7 ^ LittleEndian.ToUInt32 (header, 0x30);
    IsEncrypted     = 0 != (0xFB73A956 ^ LittleEndian.ToUInt32 (header, 0x34));
    EntryKey        = 0x7DA8F173 * Binary.RotR (entry_key, 5) + 0x13712765;
    EntryNameOffset = 0x18;
    CmvsMd5[0] = 0x43DE7C1A ^ LittleEndian.ToUInt32 (header, 0x20);
    CmvsMd5[1] = 0xCC65F416 ^ LittleEndian.ToUInt32 (header, 0x24);
    CmvsMd5[2] = 0xD016A93D ^ LittleEndian.ToUInt32 (header, 0x28);
    CmvsMd5[3] = 0x97A3BA9B ^ LittleEndian.ToUInt32 (header, 0x2C);
}
```

#### ParseV7

```csharp
private void ParseV7 (byte[] header) {
    ParseV6 (header);
    var index_key_size = LittleEndian.ToInt32 (header, 0x40);
    IndexKeySize = 0x65EF99F3 ^ index_key_size;
    InitChecksum = (uint)index_key_size - 0x6DC5A9B4u;
    EntryNameOffset = 0x1C;
}
```

#### VerifyIndex

```csharp
public bool VerifyIndex (byte[] index) {
    if (index.Length != (int)IndexSize)
        return false;
    using (var md5 = MD5.Create())
    {
        var hash = md5.ComputeHash (index);
        if (!hash.SequenceEqual (IndexMd5))
            return false;
        if (Version > 6 && IndexKeySize > 0x10)
        {
            int index_size = DirEntriesSize + FileEntriesSize;
            hash = md5.ComputeHash (index, index_size+0x10, IndexKeySize-0x10);
            if (!hash.SequenceEqual (index.Skip (index_size).Take (0x10)))
                return false;
        }
        return true;
    }
}
```

#### CheckSum

```csharp
public static uint CheckSum (byte[] data, int index, int length, uint crc) {
    if (null == data)
        throw new ArgumentNullException ("data");
    if (index < 0 || index > data.Length)
        throw new ArgumentOutOfRangeException ("index");
    if (length < 0 || length > data.Length || length > data.Length-index)
        throw new ArgumentException ("length");
    int dwords = length / 4;
    if (dwords > 0)
    {
        unsafe
        {
            fixed (byte* raw = &data[index])
            {
                uint* raw32 = (uint*)raw;
                for (int i = 0; i < dwords; ++i)
                    crc += raw32[i];
            }
        }
        index += length & -4;
    }
    for (int i = 0; i < (length & 3); ++i)
        crc += data[index+i];
    return crc;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Cmvs/CpzHeader.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
