# Tactics / ArcYU：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARC/Tactics/0` / `GameRes.Formats.Tactics.YuOpener` | `arc` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `YuOpener.TryOpen` | `uint offset = lst.ReadUInt32();` |
| `YuOpener.TryOpen` | `byte type = lst.ReadUInt8();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Tactics.YuEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public byte ContentType ;
```

### GameRes.Formats.Tactics.YuOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
const byte DefaultKey = 0x55 ;

static readonly string[] IndexExtensions = new string[] { ".dll" }

static readonly string[] KnownTypes = new string[] { "bmp", "jpg" }
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    string lst_name = IndexExtensions.Select (ext => file.Name + ext)
        .FirstOrDefault (name => VFS.FileExists (name));
    if (null == lst_name)
        return null;
    using (var lst = VFS.OpenBinaryStream (lst_name))
    {
        const int name_length = 0x41;
        var dir = new List<Entry>();
        var name_buffer = new byte[name_length];
        while (lst.Read (name_buffer, 0, name_length) == name_length)
        {
            int name_end;
            for (name_end = 0; name_end < name_length; ++name_end)
            {
                if (0 == name_buffer[name_end])
                    break;
                name_buffer[name_end] ^= DefaultKey;
            }
            var name = Binary.GetCString (name_buffer, 0, name_end);
            uint offset = lst.ReadUInt32();
            if (offset > file.MaxOffset)
                return null;
            byte type = lst.ReadUInt8();
            if (type < KnownTypes.Length)
                name = Path.ChangeExtension (name, KnownTypes[type]);
            var entry = FormatCatalog.Instance.Create<YuEntry> (name);
            entry.Offset = offset;
            entry.ContentType = type;
            dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        for (int i = 0; i < dir.Count; ++i)
        {
            long next_offset = i + 1 == dir.Count ? file.MaxOffset : dir[i+1].Offset;
            dir[i].Size = (uint)(next_offset - dir[i].Offset);
        }
        return new ArcFile (file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    var yent = entry as YuEntry;
    if (null == yent || yent.ContentType != 3)
        return input;
    return new XoredStream (input, DefaultKey);
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Tactics/ArcYU.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
