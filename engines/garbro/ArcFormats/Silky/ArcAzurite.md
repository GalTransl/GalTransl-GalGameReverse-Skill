# Silky / ArcAzurite：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/AZURITE` / `GameRes.Formats.Silky.SilkyArcOpener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SilkyArcOpener.TryOpen` | `uint index_size = file.View.ReadUInt32 (0);` |
| `SilkyArcOpener.TryOpen` | `if (0 == file.View.ReadByte (4))` |
| `SilkyArcOpener.TryOpen` | `int name_length = index.ReadByte();` |
| `SilkyArcOpener.TryOpen` | `entry.Size          = Binary.BigEndian (index.ReadUInt32());` |
| `SilkyArcOpener.TryOpen` | `entry.UnpackedSize  = Binary.BigEndian (index.ReadUInt32());` |
| `SilkyArcOpener.TryOpen` | `entry.Offset        = Binary.BigEndian (index.ReadUInt32());` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Silky.SilkyArcOpener

继承/接口：`Ai6Opener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".arc"))
        return null;
    uint index_size = file.View.ReadUInt32 (0);
    if (index_size < 10 || index_size >= file.MaxOffset-4)
        return null;
    if (0 == file.View.ReadByte (4))
        return null;

    var dir = new List<Entry>();
    using (var index = file.CreateStream (4, index_size))
    {
        var name_buffer = new byte[0x100];
        while (index.PeekByte() != -1)
        {
            int name_length = index.ReadByte();
            if (0 == name_length)
                return null;
            if (name_length != index.Read (name_buffer, 0, name_length))
                return null;
            DecryptName (name_buffer, name_length);
            var name = Encodings.cp932.GetString (name_buffer, 0, name_length);
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Size          = Binary.BigEndian (index.ReadUInt32());
            entry.UnpackedSize  = Binary.BigEndian (index.ReadUInt32());
            entry.Offset        = Binary.BigEndian (index.ReadUInt32());
            if (entry.Offset < index_size+4 || !entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.IsPacked = entry.Size != entry.UnpackedSize;
            dir.Add (entry);
        }
    }
    return new ArcFile (file, this, dir);
}
```

#### DecryptName

```csharp
static void DecryptName (byte[] buffer, int length) {
    byte key = (byte)length;
    for (int i = 0; i < length; ++i)
        buffer[i] += key--;
}
```

## 配套算法与外部条件

- [ArcFormats/Silky/ArcAi6Win.cs](ArcAi6Win.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Silky/ArcAzurite.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
