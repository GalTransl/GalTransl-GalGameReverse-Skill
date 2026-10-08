# LightVN / ArcVNDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ZIP/VNDAT` / `GameRes.Formats.LightVN.VndatOpener` | `vndat` | 无固定签名或来源表达式未解析 | `False` |

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

### GameRes.Formats.LightVN.VndatOpener

继承/接口：`ZipOpener`。

#### VndatOpener

```csharp
public VndatOpener () {
    Settings = null;
    Extensions = new string[] { "vndat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".vndat"))
        return null;
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
new ArcFile OpenZipArchive (ArcView file, Stream input) {
    var sc = SharpZip.StringCodec.FromCodePage (Encoding.UTF8.CodePage);
    var zip = new SharpZip.ZipFile (input, false, sc);
    try
    {
        var files = zip.Cast<SharpZip.ZipEntry>().Where (z => !z.IsDirectory);
        bool has_encrypted = files.Any (z => z.IsCrypted);
        if (has_encrypted)
            throw new InvalidFormatException();
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
    var data = new byte[zent.UnpackedSize];
    using (var input = zarc.Native.GetInputStream (zent.NativeEntry))
        input.Read (data, 0, data.Length);
    McdatArchive.Decrypt (data, McdatOpener.DefaultKey, 100);
    return new BinMemoryStream (data, zent.Name);
}
```

## 配套算法与外部条件

- [ArcFormats/LightVN/ArcMCDAT.cs](ArcMCDAT.md)：本页引用的随包算法资料。
- [ArcFormats/PkWare/ArcZIP.cs](../PkWare/ArcZIP.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/LightVN/ArcVNDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
