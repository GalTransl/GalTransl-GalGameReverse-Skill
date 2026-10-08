# Amaterasu / ArcAMI：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AMI` / `GameRes.Formats.Amaterasu.AmiOpener` | `ami`, `amr` | `414d4900` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `AmiOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `AmiOpener.TryOpen` | `uint base_offset = file.View.ReadUInt32 (8);` |
| `AmiOpener.TryOpen` | `uint id = file.View.ReadUInt32 (cur_offset);` |
| `AmiOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (cur_offset+4);` |
| `AmiOpener.TryOpen` | `uint size = file.View.ReadUInt32 (cur_offset+8);` |
| `AmiOpener.TryOpen` | `uint packed_size = file.View.ReadUInt32 (cur_offset+12);` |
| `AmiOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Amaterasu.AmiEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public uint Id ;

private Lazy<string> m_ext ;

private Lazy<string> m_name ;

private Lazy<string> m_type ;

public override string Name {
    get { return m_name.Value; }
    set { m_name = new Lazy<string> (() => value); }
}

public override string Type {
    get { return m_type.Value; }
    set { m_type = new Lazy<string> (() => value); }
}
```

#### AmiEntry

```csharp
public AmiEntry (uint id, Func<string> ext_factory) {
    Id = id;
    m_ext = new Lazy<string> (ext_factory);
    m_name = new Lazy<string> (GetName);
    m_type = new Lazy<string> (GetEntryType);
}
```

#### GetName

```csharp
private string GetName () {
    return string.Format ("{0:x8}.{1}", Id, m_ext.Value);
}
```

#### GetEntryType

```csharp
private string GetEntryType () {
    var ext = m_ext.Value;
    if ("grp" == ext)
        return "image";
    if ("scr" == ext)
        return "script";
    return "";
}
```

### GameRes.Formats.Amaterasu.AmiOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static Lazy<GrpFormat> s_grp_format = new Lazy<GrpFormat> (() =>
FormatCatalog.Instance.ImageFormats.OfType<GrpFormat>().FirstOrDefault()) ;
```

#### AmiOpener

```csharp
public AmiOpener () {
    Extensions = new string[] { "ami", "amr" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (count <= 0)
        return null;
    uint base_offset = file.View.ReadUInt32 (8);
    long max_offset = file.MaxOffset;
    if (base_offset >= max_offset)
        return null;

    uint cur_offset = 16;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        if (cur_offset+16 > base_offset)
            return null;
        uint id = file.View.ReadUInt32 (cur_offset);
        uint offset = file.View.ReadUInt32 (cur_offset+4);
        uint size = file.View.ReadUInt32 (cur_offset+8);
        uint packed_size = file.View.ReadUInt32 (cur_offset+12);

        var entry = new AmiEntry (id, () => {
            uint signature = file.View.ReadUInt32 (offset);
            if (0x00524353 == signature)
                return "scr";
            else if (0 != packed_size || 0x00505247 == signature)
                return "grp";
            else
                return "dat";
        });

        entry.Offset = offset;
        entry.UnpackedSize = size;
        entry.IsPacked = 0 != packed_size;
        entry.Size   = entry.IsPacked ? packed_size : size;
        if (!entry.CheckPlacement (max_offset))
            return null;
        dir.Add (entry);
        cur_offset += 16;
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = base.OpenEntry (arc, entry);
    var packed_entry = entry as AmiEntry;
    if (null == packed_entry || !packed_entry.IsPacked)
        return input;
    else
        return new ZLibStream (input, CompressionMode.Decompress);
}
```

#### UpdateFileTable

```csharp
int UpdateFileTable (IDictionary<uint, PackedEntry> table, IEnumerable<Entry> list) {
    int update_count = 0;
    foreach (var entry in list)
    {
        if (entry.Type != "image" && !entry.Name.HasExtension (".scr"))
            continue;
        uint id;
        if (!uint.TryParse (Path.GetFileNameWithoutExtension (entry.Name), NumberStyles.HexNumber,
                            CultureInfo.InvariantCulture, out id))
            continue;
        PackedEntry existing;
        if (table.TryGetValue (id, out existing) && !(existing is AmiEntry))
        {
            var file_new = new FileInfo (entry.Name);
            if (!file_new.Exists)
                continue;
            var file_old = new FileInfo (existing.Name);
            if (file_new.LastWriteTime <= file_old.LastWriteTime)
                continue;
        }
        table[id] = new PackedEntry
        {
            Name = entry.Name,
            Type = entry.Type
        };
        ++update_count;
    }
    return update_count;
}
```

#### CopyAmiEntry

```csharp
void CopyAmiEntry (ArcFile base_archive, Entry entry, Stream output) {
    using (var input = base_archive.File.CreateStream (entry.Offset, entry.Size))
        input.CopyTo (output);
}
```

#### WriteAmiEntry

```csharp
uint WriteAmiEntry (PackedEntry entry, Stream output) {
    uint packed_size = 0;
    using (var input = VFS.OpenBinaryStream (entry))
    {
        long file_size = input.Length;
        if (file_size > uint.MaxValue)
            throw new FileSizeException();
        entry.UnpackedSize = (uint)file_size;
        if ("image" == entry.Type)
        {
            packed_size = WriteImageEntry (entry, input, output);
        }
        else
        {
            input.AsStream.CopyTo (output);
        }
    }
    return packed_size;
}
```

#### WriteImageEntry

```csharp
uint WriteImageEntry (PackedEntry entry, IBinaryStream input, Stream output) {
    var grp = s_grp_format.Value;
    if (null == grp)
        throw new FileFormatException ("GRP image encoder not available");
    bool is_grp = grp.Signature == input.Signature;
    input.Position = 0;
    var start = output.Position;
    using (var zstream = new ZLibStream (output, CompressionMode.Compress, CompressionLevel.Level9, true))
    {
        if (is_grp)
        {
            input.AsStream.CopyTo (zstream);
        }
        else
        {
            var image = ImageFormat.Read (input);
            if (null == image)
                throw new InvalidFormatException (string.Format (arcStrings.MsgInvalidImageFormat, entry.Name));
            grp.Write (zstream, image);
            entry.UnpackedSize = (uint)zstream.TotalIn;
        }
    }
    return (uint)(output.Position - start);
}
```

## 配套算法与外部条件

- [ArcFormats/Amaterasu/ImageGRP.cs](ImageGRP.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Amaterasu/ArcAMI.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
