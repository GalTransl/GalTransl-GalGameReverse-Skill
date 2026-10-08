# Dac / ArcDPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DPK` / `GameRes.Formats.Dac.DpkOpener` | `dpk` | `44504b00` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DpkOpener.TryOpen` | `int data_offset = LittleEndian.ToInt32 (header, 0);` |
| `DpkOpener.TryOpen` | `int count = LittleEndian.ToInt32 (index, 0);` |
| `DpkOpener.TryOpen` | `var index_offset = base_offset + LittleEndian.ToInt32 (index, 4+i*4);` |
| `DpkOpener.TryOpen` | `uint size = LittleEndian.ToUInt32 (index, index_offset + 4);` |
| `DpkOpener.TryOpen` | `Offset = data_offset + LittleEndian.ToUInt32 (index, index_offset),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Dac.DpkOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public uint Key1 ;

public uint Key2 ;
```

### GameRes.Formats.Dac.DpkScheme

#### 状态与常量

```csharp
public uint            Key1 { get; set; }

public uint            Key2 { get; set; }

public string          Name { get; set; }

public string OriginalTitle { get; set; }
```

### GameRes.Formats.Dac.DpkEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Hash ;
```

### GameRes.Formats.Dac.DpkArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly uint Key1 ;

public readonly uint Key2 ;
```

#### DpkArchive

```csharp
public DpkArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, DpkOptions opt)
    : base (arc, impl, dir) {
    Key1 = opt.Key1;
    Key2 = opt.Key2;
}
```

### GameRes.Formats.Dac.DpkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
public static DpkScheme[] KnownSchemes = new DpkScheme[0] ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var header = new byte[8];
    if (8 != file.View.Read (8, header, 0, 8))
        return null;
    byte last = header[7];
    for (int i = 0; i < 8; i++)
    {
        header[i] ^= (byte)(i - 8);
    }
    int data_offset = LittleEndian.ToInt32 (header, 0);
    if (data_offset <= 16 || data_offset >= file.MaxOffset)
        return null;
    int index_length = data_offset - 16;
    var index = new byte[index_length];
    if (index_length != file.View.Read (16, index, 0, (uint)index_length))
        return null;
    DecryptIndex (index, 16, index_length, last);
    int count = LittleEndian.ToInt32 (index, 0);
    if (count <= 0 || count > 0xfffff)
        return null;

    var options = Query<DpkOptions> (arcStrings.ArcEncryptedNotice);
    var name_bytes = new byte[0x20];
    var dir = new List<Entry> (count);
    int base_offset = 4 + count * 4;
    for (int i = 0; i < count; ++i)
    {
        var index_offset = base_offset + LittleEndian.ToInt32 (index, 4+i*4);
        int name_begin = index_offset+0x0c;
        int name_end = Array.IndexOf (index, (byte)0, name_begin);
        if (-1 == name_end)
            name_end = index.Length;
        if (name_end == name_begin)
            continue;
        if ('z' == index[name_end-1])
            --name_end;

        int name_length = name_end - name_begin;
        var name = Encodings.cp932.GetString (index, name_begin, name_length);
        if (name_length > name_bytes.Length)
            name_bytes = new byte[name_length];

        string name_base = Path.GetFileName (name);
        name_length = Encodings.cp932.GetBytes (name_base, 0, name_base.Length, name_bytes, 0);

        uint size = LittleEndian.ToUInt32 (index, index_offset + 4);
        var entry = new DpkEntry
        {
            Name = name,
            Type = FormatCatalog.Instance.GetTypeFromName (name),
            Hash = GetNameHash (name_bytes, 0, name_length, options.Key1, options.Key2, size),
            Offset = data_offset + LittleEndian.ToUInt32 (index, index_offset),
            Size = size,
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    if (0 == dir.Count)
        return null;
    return new DpkArchive (file, this, dir, options);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var parc = arc as DpkArchive;
    var pentry = entry as DpkEntry;
    if (null == parc || null == pentry)
        return arc.File.CreateStream (entry.Offset, entry.Size);
    var data = new byte[entry.Size];
    arc.File.View.Read (entry.Offset, data, 0, entry.Size);
    DecryptEntry (data, parc.Key1, parc.Key2, pentry);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptIndex

```csharp
private void DecryptIndex (byte[] buf, int base_offset, int length, byte last) {
    for (int i = 0; i < length; i++)
    {
        int key = base_offset + i + last;
        last = buf[i];
        buf[i] ^= (byte)key;
    }
}
```

#### DecryptEntry

```csharp
private void DecryptEntry (byte[] data, uint key1, uint key2, DpkEntry entry) {
    for (uint i = 0; i < data.Length; ++i)
    {
        data[i] ^= (byte)(key1 + (key1 >> 8));
        data[i] -= (byte)entry.Hash;
        key1 += key2;
    }
}
```

#### GetNameHash

```csharp
private uint GetNameHash (byte[] name, int begin, int length, uint key1, uint key2, uint entry_size) {
    uint hash = 0;
    for (int i = begin+length-1; i >= begin; --i)
    {
        hash += key1 + key2 * (entry_size + name[i]);
    }
    return hash;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Dac/ArcDPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
