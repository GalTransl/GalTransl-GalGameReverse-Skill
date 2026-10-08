# PkWare / ArcZIP：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ZIP` / `GameRes.Formats.PkWare.ZipOpener` | `zip` | 无固定签名或来源表达式未解析 | `True` |

## 类型别名

| 摘录中的名称 | 来源类型 |
|---|---|
| `SharpZip` | `ICSharpCode.SharpZipLib.Zip` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.PkWare.ZipEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public readonly SharpZip.ZipEntry NativeEntry ;
```

#### ZipEntry

```csharp
public ZipEntry (SharpZip.ZipEntry zip_entry) {
    NativeEntry = zip_entry;
    Name = zip_entry.Name;
    Type = FormatCatalog.Instance.GetTypeFromName (zip_entry.Name);
    IsPacked = true;

    Size = (uint)Math.Min (zip_entry.CompressedSize, uint.MaxValue);
    UnpackedSize = (uint)Math.Min (zip_entry.Size, uint.MaxValue);
    Offset = zip_entry.Offset;
}
```

### GameRes.Formats.PkWare.PkZipArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
readonly SharpZip.ZipFile m_zip ;

public SharpZip.ZipFile Native { get { return m_zip; } }

bool _zip_disposed = false ;
```

#### PkZipArchive

```csharp
public PkZipArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, SharpZip.ZipFile native)
    : base (arc, impl, dir) {
    m_zip = native;
}
```

### GameRes.Formats.PkWare.ZipOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
internal static readonly byte[] PkDirSignature = { (byte)'P', (byte)'K', 5, 6 }

EncodingSetting ZipEncoding = new EncodingSetting ("ZIPEncodingCP", "DefaultEncoding") ;

ZipScheme DefaultScheme = new ZipScheme { KnownKeys = new Dictionary<string, string>() }
```

#### ZipOpener

```csharp
public ZipOpener () {
    Settings = new[] { ZipEncoding };
    Extensions = new string[] { "zip" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (-1 == SearchForSignature (file, PkDirSignature))
        return null;
    var input = file.CreateStream();
    try
    {
        return OpenZipArchive (file, input);
    }
    catch
    {
        input.Dispose();
        throw;
    }
}
```

#### OpenZipArchive

```csharp
internal ArcFile OpenZipArchive (ArcView file, Stream input) {
    var sc = SharpZip.StringCodec.FromCodePage (Properties.Settings.Default.ZIPEncodingCP);
    var zip = new SharpZip.ZipFile (input, false, sc);
    try
    {
        var files = zip.Cast<SharpZip.ZipEntry>().Where (z => !z.IsDirectory);
        bool has_encrypted = files.Any (z => z.IsCrypted);
        if (has_encrypted)
            zip.Password = QueryPassword (file);
        var dir = files.Select (z => new ZipEntry (z) as Entry).ToList();
        return new PkZipArchive (file, this, dir, zip);
    }
    catch
    {
        zip.Close();
        throw;
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var zarc = (PkZipArchive)arc;
    var zent = (ZipEntry)entry;
    return zarc.Native.GetInputStream (zent.NativeEntry);
}
```

#### SearchForSignature

```csharp
internal unsafe long SearchForSignature (ArcView file, byte[] signature) {
    if (signature.Length < 4)
        throw new ArgumentException ("Invalid ZIP file signature", "signature");

    uint tail_size = (uint)Math.Min (file.MaxOffset, 0x10016L);
    if (tail_size < 0x16)
        return -1;
    var start_offset = file.MaxOffset - tail_size;
    using (var view = file.CreateViewAccessor (start_offset, tail_size))
    using (var pointer = new ViewPointer (view, start_offset))
    {
        byte* ptr_end = pointer.Value;
        byte* ptr = ptr_end + tail_size-0x16;
        for (; ptr >= ptr_end; --ptr)
        {
            if (signature[3] == ptr[3] && signature[2] == ptr[2] &&
                signature[1] == ptr[1] && signature[0] == ptr[0])
                return start_offset + (ptr-ptr_end);
        }
        return -1;
    }
}
```

#### QueryPassword

```csharp
string QueryPassword (ArcView file) {
    var options = Query<ZipOptions> (arcStrings.ZIPEncryptedNotice);
    return options.Password;
}
```

### GameRes.Formats.PkWare.ZipOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public CompressionLevel CompressionLevel { get; set; }

public         Encoding FileNameEncoding { get; set; }

public           string         Password { get; set; }
```

## 配套算法与外部条件

- [ArcFormats/ResourceSettings.cs](../ResourceSettings.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/PkWare/ArcZIP.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
