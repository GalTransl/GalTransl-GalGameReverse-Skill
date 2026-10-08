# GsPack / ArcGsPack：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `GsData` / `GameRes.Formats.Gs.DatOpener` | `dat` | `47735359` | `False` |
| `GsPack` / `GameRes.Formats.Gs.PakOpener` | `pak`, `dat`, `pa_` | `44617461`, `47735061` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `if (!(file.View.AsciiEqual (0, "DataPack5") \|\|` |
| `PakOpener.TryOpen` | `file.View.AsciiEqual (0, "GsPack5") \|\|` |
| `PakOpener.TryOpen` | `file.View.AsciiEqual (0, "GsPack4")))` |
| `PakOpener.TryOpen` | `int version_minor = file.View.ReadUInt16 (0x30);` |
| `PakOpener.TryOpen` | `int version_major = file.View.ReadUInt16 (0x32);` |
| `PakOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0x34);` |
| `PakOpener.TryOpen` | `int count = file.View.ReadInt32 (0x3c);` |
| `PakOpener.TryOpen` | `uint is_encrypted = file.View.ReadUInt32 (0x38);` |
| `PakOpener.TryOpen` | `long data_offset = file.View.ReadUInt32 (0x40);` |
| `PakOpener.TryOpen` | `int index_offset = file.View.ReadInt32 (0x44);` |
| `PakOpener.TryOpen` | `byte[] packed_index = file.View.ReadBytes (index_offset, index_size);` |
| `PakOpener.TryOpen` | `index = file.View.ReadBytes (index_offset, (uint)unpacked_size);` |
| `PakOpener.TryOpen` | `Offset = data_offset + LittleEndian.ToUInt32 (index, index_offset+0x40),` |
| `PakOpener.TryOpen` | `Size = LittleEndian.ToUInt32 (index, index_offset+0x44),` |
| `PakOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |
| `PakOpener.OpenEntry` | `var data = garc.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `DatOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "GsSYMBOL5BINDATA"))` |
| `DatOpener.TryOpen` | `uint header_size = file.View.ReadUInt32 (0xa4);` |
| `DatOpener.TryOpen` | `int count = file.View.ReadInt32 (0xa8);` |
| `DatOpener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (0xb8);` |
| `DatOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0xbc);` |
| `DatOpener.TryOpen` | `uint crypt_key = file.View.ReadUInt32 (0xc0);` |
| `DatOpener.TryOpen` | `uint unpacked_index_size = file.View.ReadUInt32 (0xc4);` |
| `DatOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (0xc8);` |
| `DatOpener.TryOpen` | `Offset = data_offset + LittleEndian.ToUInt32 (index, (int)index_offset),` |
| `DatOpener.TryOpen` | `Size = LittleEndian.ToUInt32 (index, (int)index_offset + 4),` |
| `DatOpener.TryOpen` | `UnpackedSize = LittleEndian.ToUInt32 (index, (int)index_offset + 8),` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Gs.GsPackArchive

继承/接口：`ArcFile`。

### GameRes.Formats.Gs.PakOpener

继承/接口：`ArchiveFormat`。

#### PakOpener

```csharp
public PakOpener () {
    Extensions = new string[] { "pak", "dat", "pa_" };
    Signatures = new   uint[] { 0x61746144, 0x61507347 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!(file.View.AsciiEqual (0, "DataPack5") ||
          file.View.AsciiEqual (0, "GsPack5") ||
          file.View.AsciiEqual (0, "GsPack4")))
        return null;
    int version_minor = file.View.ReadUInt16 (0x30);
    int version_major = file.View.ReadUInt16 (0x32);
    uint index_size = file.View.ReadUInt32 (0x34);
    int count = file.View.ReadInt32 (0x3c);
    if (!IsSaneCount (count) || index_size > 0xffffff)
        return null;
    uint is_encrypted = file.View.ReadUInt32 (0x38);
    long data_offset = file.View.ReadUInt32 (0x40);
    int index_offset = file.View.ReadInt32 (0x44);
    int entry_size = version_major < 5 ? 0x48 : 0x68;
    int unpacked_size = count * entry_size;
    byte[] index;
    if (index_size != 0)
    {
        byte[] packed_index = file.View.ReadBytes (index_offset, index_size);
        if (index_size != packed_index.Length)
            return null;
        if (0 != (is_encrypted & 1))
            for (int i = 0; i != packed_index.Length; ++i)
                packed_index[i] ^= (byte)i;
        using (var stream = new MemoryStream (packed_index))
        using (var reader = new LzssReader (stream, packed_index.Length, unpacked_size))
        {
            reader.Unpack();
            index = reader.Data;
        }
    }
    else
    {
        index = file.View.ReadBytes (index_offset, (uint)unpacked_size);
    }
    index_offset = 0;
    string default_type = "";
    var arc_name = Path.GetFileNameWithoutExtension (file.Name);
    if (arc_name.StartsWith ("image", StringComparison.OrdinalIgnoreCase))
        default_type = "image";
    else if (arc_name.StartsWith ("voice", StringComparison.OrdinalIgnoreCase))
        default_type = "audio";
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = Binary.GetCString (index, index_offset, 0x40);
        if (0 != name.Length)
        {
            var entry = new Entry {
                Name = name,
                Type = default_type,
                Offset = data_offset + LittleEndian.ToUInt32 (index, index_offset+0x40),
                Size = LittleEndian.ToUInt32 (index, index_offset+0x44),
            };
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
        }
        index_offset += entry_size;
    }
    if (0 != (is_encrypted & 2))
        return new GsPackArchive (file, this, dir);

    if (string.IsNullOrEmpty (default_type))
    {
        foreach (var entry in dir)
        {
            uint signature = file.View.ReadUInt32 (entry.Offset);
            var res = AutoEntry.DetectFileType (signature);
            entry.ChangeType (res);
        }
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var garc = arc as GsPackArchive;
    if (null == garc)
        return base.OpenEntry (arc, entry);
    var data = garc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecryptData (data, entry.Name);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, string key) {
    int numkey = 0;
    for (int i = 0; i < key.Length; ++i)
        numkey = numkey * 37 + (key[i] | 0x20);
    unsafe
    {
        fixed (byte* data8 = data)
        {
            int* data32 = (int*)data8;
            for (int count = data.Length / 4; count > 0; --count)
                *data32++ ^= numkey;
        }
    }
}
```

### GameRes.Formats.Gs.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "GsSYMBOL5BINDATA"))
        return null;
    uint header_size = file.View.ReadUInt32 (0xa4);
    if (header_size < 0xd0)
        return null;
    int count = file.View.ReadInt32 (0xa8);
    uint index_offset = file.View.ReadUInt32 (0xb8);
    uint index_size = file.View.ReadUInt32 (0xbc);
    uint crypt_key = file.View.ReadUInt32 (0xc0);
    uint unpacked_index_size = file.View.ReadUInt32 (0xc4);
    if (count * 0x18 != unpacked_index_size)
        return null;
    uint data_offset = file.View.ReadUInt32 (0xc8);
    byte[] packed_index = new byte[index_size];
    if (index_size != file.View.Read (index_offset, packed_index, 0, index_size))
        return null;
    if (0 != crypt_key)
        for (int i = 0; i != packed_index.Length; ++i)
            packed_index[i] ^= (byte)(i & crypt_key);
    using (var stream = new MemoryStream (packed_index))
    using (var reader = new LzssReader (stream, packed_index.Length, (int)unpacked_index_size))
    {
        reader.Unpack();
        var index = reader.Data;
        index_offset = 0;
        var dir = new List<Entry> (count);
        for (int i = 0; i < count; ++i)
        {
            var entry = new PackedEntry
            {
                Name = i.ToString ("D5"),
                Offset = data_offset + LittleEndian.ToUInt32 (index, (int)index_offset),
                Size = LittleEndian.ToUInt32 (index, (int)index_offset + 4),
                UnpackedSize = LittleEndian.ToUInt32 (index, (int)index_offset + 8),
            };
            dir.Add (entry);
            index_offset += 0x18;
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        return Stream.Null;
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (entry is PackedEntry)
        return new LzssStream (input);
    return input;
}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/GsPack/ArcGsPack.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
