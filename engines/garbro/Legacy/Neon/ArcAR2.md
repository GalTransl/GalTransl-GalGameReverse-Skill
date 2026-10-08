# Neon / ArcAR2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `AR2/NEON` / `GameRes.Formats.Neon.Ar2Opener` | `ar2` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Ar2Opener.TryOpen` | `\|\| file.View.ReadUInt32 (8) != uKey` |
| `Ar2Opener.TryOpen` | `\|\| file.View.ReadUInt32 (0) != file.View.ReadUInt32 (4)` |
| `Ar2Opener.TryOpen` | `\|\| (file.View.ReadUInt32 (0xC) ^ uKey) > 0x100)` |
| `Ar2Opener.TryOpen` | `uint size = buffer.ToUInt32 (0);` |
| `Ar2Opener.TryOpen` | `int name_length = buffer.ToInt32 (0xC);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Neon.Ar2Opener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const byte DefaultKey = 0x55 ;
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint uKey = DefaultKey | DefaultKey << 16;
    uKey |= uKey << 8;
    if (file.MaxOffset <= 0x10
        || file.View.ReadUInt32 (8) != uKey
        || file.View.ReadUInt32 (0) != file.View.ReadUInt32 (4)
        || (file.View.ReadUInt32 (0xC) ^ uKey) > 0x100)
        return null;
    using (var stream = file.CreateStream())
    using (var input = new XoredStream (stream, DefaultKey))
    {
        var buffer = new byte[0x100];
        var dir = new List<Entry>();
        while (0x10 == input.Read (buffer, 0, 0x10))
        {
            uint size = buffer.ToUInt32 (0);

            int name_length = buffer.ToInt32 (0xC);
            if (0 == size && 0 == name_length)
                continue;
            if (name_length <= 0 || name_length > buffer.Length)
                return null;
            input.Read (buffer, 0, name_length);
            var name = Encodings.cp932.GetString (buffer, 0, name_length);
            var entry = Create<Entry> (name);
            entry.Offset = input.Position;
            entry.Size = size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            dir.Add (entry);
            input.Seek (size, SeekOrigin.Current);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new XoredStream (input, DefaultKey);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../../ArcFormats/CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Neon/ArcAR2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
