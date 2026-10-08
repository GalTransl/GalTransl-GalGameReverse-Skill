# Abogado / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/ABOGADO` / `GameRes.Formats.Abogado.PakOpener` | `pak` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `int count = file.View.ReadInt16 (0);` |
| `PakOpener.TryOpen` | `int encryption = file.View.ReadInt16 (2);` |
| `PakOpener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x40);` |
| `PakOpener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x40);` |
| `PakOpener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x44);` |
| `PakOpener.OpenEntry` | `int key = arc.File.View.ReadInt32 (enc_offset);` |
| `PakOpener.OpenEntry` | `var data = input.ReadBytes ((int)entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Abogado.Fs8Archive

继承/接口：`ArcFile`。

### GameRes.Formats.Abogado.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly Lazy<byte[][]> DefaultKeys = new Lazy<byte[][]> (LoadKeys) ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt16 (0);
    if (!IsSaneCount (count))
        return null;
    int encryption = file.View.ReadInt16 (2);
    if (encryption < 0 || encryption > 1)
        return null;

    uint index_offset = 4;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x40);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = file.View.ReadUInt32 (index_offset+0x40);
        entry.Size   = file.View.ReadUInt32 (index_offset+0x44);
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x48;
    }
    if (encryption != 0)
        return new Fs8Archive (file, this, dir);
    else
        return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    if (!(arc is Fs8Archive))
        return input;
    var enc_offset = entry.Offset + entry.Size;
    int key = arc.File.View.ReadInt32 (enc_offset);
    if (key < 0 || key >= DefaultKeys.Value.Length)
        return input;
    using (input)
    {
        var data = input.ReadBytes ((int)entry.Size);
        FsDecrypt (data, DefaultKeys.Value[key]);
        return new BinMemoryStream (data, entry.Name);
    }
}
```

#### FsDecrypt

```csharp
void FsDecrypt (byte[] data, byte[] key) {
    for (int i = 0; i < data.Length; ++i)
    {
        data[i] = key[data[i]];
    }
}
```

#### LoadKeys

```csharp
static byte[][] LoadKeys () {
    using (var input = EmbeddedResource.Open ("keytable.dat", typeof (PakOpener)))
    {
        if (null == input)
            return Array.Empty<byte[]>();
        var keys = new List<byte[]> (128);
        for (int i = 0; i < 128; ++i)
        {
            var k = new byte[256];
            if (input.Read (k, 0, 256) != 256)
                break;
            keys.Add (k);
        }
        return keys.ToArray();
    }
}
```

## 配套算法与外部条件

- [ArcFormats/EmbeddedResource.cs](../EmbeddedResource.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Abogado/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
