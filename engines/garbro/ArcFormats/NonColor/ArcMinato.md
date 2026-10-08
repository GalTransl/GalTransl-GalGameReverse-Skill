# NonColor / ArcMinato：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/MINATO` / `GameRes.Formats.Minato.MinatoDatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `MinatoDatOpener.TryOpen` | `int count = Binary.BigEndian (file.View.ReadInt32 (0)) ^ SignatureKey;` |
| `MinatoIndexReader.ReadEntry` | `uint key            = Binary.BigEndian (m_input.ReadUInt32());` |
| `MinatoIndexReader.ReadEntry` | `int  flags          = m_input.ReadUInt8() ^ (byte)key;` |
| `MinatoIndexReader.ReadEntry` | `uint offset         = Binary.BigEndian (m_input.ReadUInt32()) ^ key;` |
| `MinatoIndexReader.ReadEntry` | `uint packed_size    = Binary.BigEndian (m_input.ReadUInt32()) ^ key;` |
| `MinatoIndexReader.ReadEntry` | `uint unpacked_size  = Binary.BigEndian (m_input.ReadUInt32()) ^ key;` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Minato.MinatoDatOpener

继承/接口：`NonColor.DatOpener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (!file.Name.HasExtension (".dat"))
        return null;
    int count = Binary.BigEndian (file.View.ReadInt32 (0)) ^ SignatureKey;
    if (!IsSaneCount (count))
        return null;

    var scheme = QueryScheme (file.Name);
    if (null == scheme)
        return null;

    using (var index = new MinatoIndexReader (file, count))
        return index.Read (this, scheme);
}
```

### GameRes.Formats.Minato.MinatoIndexReader

继承/接口：`NcIndexReaderBase`。

#### MinatoIndexReader

```csharp
public MinatoIndexReader (ArcView file, int count) : base (file, count) {
    ExtendByteSign = true;
}
```

#### ReadEntry

```csharp
protected override ArcDatEntry ReadEntry () {
    uint key            = Binary.BigEndian (m_input.ReadUInt32());
    int  flags          = m_input.ReadUInt8() ^ (byte)key;
    uint offset         = Binary.BigEndian (m_input.ReadUInt32()) ^ key;
    uint packed_size    = Binary.BigEndian (m_input.ReadUInt32()) ^ key;
    uint unpacked_size  = Binary.BigEndian (m_input.ReadUInt32()) ^ key;
    return new ArcDatEntry {
        Hash   = key,
        Flags  = flags,
        Offset = offset,
        Size   = packed_size,
        UnpackedSize = unpacked_size,
        IsPacked = 0 != (flags & 2),
    };
}
```

## 配套算法与外部条件

- [ArcFormats/NonColor/ArcDAT.cs](ArcDAT.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/NonColor/ArcMinato.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
