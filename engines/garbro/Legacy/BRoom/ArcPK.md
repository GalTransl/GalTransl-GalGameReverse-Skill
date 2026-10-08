# BRoom / ArcPK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PK/B-ROOM/E` / `GameRes.Formats.BRoom.EncryptedPkOpener` | `pk` | 无固定签名或来源表达式未解析 | `False` |
| `PK/B-ROOM` / `GameRes.Formats.BRoom.PkOpener` | `pk`, `cpc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PkOpener.TryOpen` | `int count = file.View.ReadInt32 (0);` |
| `PkOpener.TryOpen` | `uint size = file.View.ReadUInt32 (index_offset+4);` |
| `PkOpener.TryOpen` | `var name = file.View.ReadString (index_offset+8, 0x10);` |
| `EncryptedPkOpener.TryOpen` | `int count = (int)(file.View.ReadUInt32 (0) ^ 0xFF559977);` |
| `EncryptedPkOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `EncryptedPkOpener.TryOpen` | `uint size = file.View.ReadUInt32 (index_offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.BRoom.PkOpener

继承/接口：`ArchiveFormat`。

#### PkOpener

```csharp
public PkOpener () {
    Extensions = new[] { "pk", "cpc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (0);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 4;
    long data_offset = count * 0x18 + index_offset;
    if (data_offset >= file.MaxOffset)
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint size = file.View.ReadUInt32 (index_offset+4);
        var name = file.View.ReadString (index_offset+8, 0x10);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        var entry = Create<Entry> (name);
        entry.Offset = data_offset;
        entry.Size = size;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        data_offset += size;
        index_offset += 0x18;
    }
    if (data_offset != file.MaxOffset)
        return null;
    return new ArcFile (file, this, dir);
}
```

### GameRes.Formats.BRoom.EncryptedPkOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] DefaultNameKey = {
    0xF5, 0xB2, 0xA4, 0x45, 0x59, 0x0F, 0x15, 0x22, 0x43, 0x0B, 0x99, 0x3C, 0xDD, 0xE2
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = (int)(file.View.ReadUInt32 (0) ^ 0xFF559977);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 4;
    long data_offset = count * 0x18 + index_offset;
    if (data_offset >= file.MaxOffset)
        return null;
    var name_key = DefaultNameKey;
    var name_buffer = new byte[0x10];
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        uint size = file.View.ReadUInt32 (index_offset+4);
        file.View.Read (index_offset+8, name_buffer, 0, 14);
        uint checksum = 0;
        int j;
        for (j = 0; j < 14; ++j)
        {
            name_buffer[j] ^= name_key[j];
            if (0 == name_buffer[j])
                break;
            checksum += (uint)name_buffer[j] << ((j & 3) << 3);
        }
        checksum &= 0x3FF;
        var name = Encodings.cp932.GetString (name_buffer, 0, j);
        if (string.IsNullOrWhiteSpace (name))
            return null;
        if (name.HasAnyOfExtensions ("", "e", "er"))
            name = Path.ChangeExtension (name, ".Erp");
        var entry = Create<Entry> (name);
        entry.Offset = offset ^ checksum ^ 0x35846;
        entry.Size   = size   ^ checksum ^ 0x57982525;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 0x18;
    }
    return new ArcFile (file, this, dir);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/BRoom/ArcPK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
