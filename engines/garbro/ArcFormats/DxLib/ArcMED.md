# DxLib / ArcMED：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `MED` / `GameRes.Formats.DxLib.MedOpener` | `med` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MedOpener.TryOpen` | `if (!file.View.AsciiEqual (0, "MD"))` |
| `MedOpener.TryOpen` | `uint entry_length = file.View.ReadUInt16 (4);` |
| `MedOpener.TryOpen` | `int count = file.View.ReadUInt16 (6);` |
| `MedOpener.TryOpen` | `var name = file.View.ReadString (index_offset, name_length);` |
| `MedOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset+4);` |
| `MedOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (offset);` |
| `MedOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset);` |
| `MedOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.DxLib.MedOptions

继承/接口：`ResourceOptions`。

#### 状态与常量

```csharp
public IScriptEncryption Encryption ;
```

### GameRes.Formats.DxLib.ScrMedArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly IScriptEncryption Encryption ;
```

#### ScrMedArchive

```csharp
public ScrMedArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IScriptEncryption enc)
    : base (arc, impl, dir) {
    Encryption = enc;
}
```

### GameRes.Formats.DxLib.MedOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly ResourceInstance<ImageFormat> PrsFormat = new ResourceInstance<ImageFormat> ("PRS") ;

static ScrMedScheme DefaultScheme = new ScrMedScheme {
    KnownSchemes = new Dictionary<string, IScriptEncryption>()
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.View.AsciiEqual (0, "MD"))
        return null;
    uint entry_length = file.View.ReadUInt16 (4);
    int count = file.View.ReadUInt16 (6);
    if (entry_length <= 8 || !IsSaneCount (count))
        return null;

    uint name_length = entry_length - 8;
    uint index_offset = 0x10;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, name_length);
        index_offset += name_length;
        uint offset = file.View.ReadUInt32 (index_offset+4);

        var entry = new AutoEntry (name, () => {
            uint signature = file.View.ReadUInt32 (offset);
            if (0x4259 == (signature & 0xFFFF))
                return PrsFormat.Value;
            return AutoEntry.DetectFileType (signature);
        });
        entry.Size   = file.View.ReadUInt32 (index_offset);
        entry.Offset = offset;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 8;
    }
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    if (base_name.EndsWith ("_scr", StringComparison.OrdinalIgnoreCase)
        && KnownSchemes.Count > 0)
    {
        var encryption = QueryEncryption (file.Name);
        if (encryption != null)
            return new ScrMedArchive (file, this, dir, encryption);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var scr_arc = arc as ScrMedArchive;
    if (null == scr_arc || entry.Size <= scr_arc.Encryption.StartOffset)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    if (scr_arc.Encryption.IsEncrypted (data))
    {
        var offset = scr_arc.Encryption.StartOffset;
        scr_arc.Encryption.Decrypt (data, offset, data.Length-offset);
    }
    return new BinMemoryStream (data, entry.Name);
}
```

#### GetEncryption

```csharp
public static IScriptEncryption GetEncryption (string scheme) {
    IScriptEncryption enc;
    if (string.IsNullOrEmpty (scheme) || !KnownSchemes.TryGetValue (scheme, out enc))
        return null;
    return enc;
}
```

#### QueryEncryption

```csharp
IScriptEncryption QueryEncryption (string arc_name) {
    var title = FormatCatalog.Instance.LookupGame (arc_name);
    if (!string.IsNullOrEmpty (title) && KnownSchemes.ContainsKey (title))
        return KnownSchemes[title];
    var options = Query<MedOptions> (arcStrings.ArcEncryptedNotice);
    return options.Encryption;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/DxLib/ArcMED.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
