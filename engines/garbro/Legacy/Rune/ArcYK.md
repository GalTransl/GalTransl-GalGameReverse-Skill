# Rune / ArcYK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `YK` / `GameRes.Formats.Rune.YkOpener` | `yk` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `YkOpener.TryOpen` | `if ((file.View.ReadInt32 (0) \| file.View.ReadInt32 (4) \| file.View.ReadInt32 (8)) != 0)` |
| `YkOpener.TryOpen` | `int key = file.View.ReadInt32 (0x10);` |
| `YkOpener.TryOpen` | `int count = file.View.ReadInt32 (0x14);` |
| `YkOpener.TryOpen` | `int id = file.View.ReadInt32 (index_offset);` |
| `YkOpener.TryOpen` | `Offset = file.View.ReadUInt32 (index_offset+4),` |
| `YkOpener.TryOpen` | `Size   = file.View.ReadUInt32 (index_offset+8),` |
| `YkOpener.TryOpen` | `var names = file.View.ReadBytes (names_entry.Offset, names_entry.Size);` |
| `YkOpener.TryOpen` | `int id = input.ReadInt32();` |
| `YkOpener.TryOpen` | `var name = input.ReadCString();` |
| `YkOpener.OpenEntry` | `var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Rune.YkArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
public readonly int Key ;
```

#### YkArchive

```csharp
public YkArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, int key)
    : base (arc, impl, dir) {
    Key = key;
}
```

### GameRes.Formats.Rune.YkOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if ((file.View.ReadInt32 (0) | file.View.ReadInt32 (4) | file.View.ReadInt32 (8)) != 0)
        return null;
    int key = file.View.ReadInt32 (0x10);
    int count = file.View.ReadInt32 (0x14);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = 0x18;
    var index = new Dictionary<int, Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        int id = file.View.ReadInt32 (index_offset);
        var entry = new Entry {
            Offset = file.View.ReadUInt32 (index_offset+4),
            Size   = file.View.ReadUInt32 (index_offset+8),
        };
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        index[id] = entry;
        index_offset += 12;
    }
    var names_entry = index[0];
    var names = file.View.ReadBytes (names_entry.Offset, names_entry.Size);
    if (key != 0)
        DecryptData (names, key);
    using (var input = new BinMemoryStream (names))
    {
        while (input.PeekByte() != -1)
        {
            int id = input.ReadInt32();
            var name = input.ReadCString();
            if (!string.IsNullOrEmpty (name))
            {
                var entry = index[id];
                entry.Name = name;
                entry.Type = FormatCatalog.Instance.GetTypeFromName (name);
            }
        }
    }
    var dir = index.Values.Where (e => !string.IsNullOrEmpty (e.Name)).ToList();
    return new YkArchive (file, this, dir, key);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var yarc = arc as YkArchive;
    if (null == yarc || 0 == yarc.Key)
        return base.OpenEntry (arc, entry);
    var data = arc.File.View.ReadBytes (entry.Offset, entry.Size);
    DecryptData (data, yarc.Key);
    return new BinMemoryStream (data, entry.Name);
}
```

#### DecryptData

```csharp
void DecryptData (byte[] data, int key) {
    for (int i = 0; i < data.Length; ++i)
    {
        uint shift = (uint)(92 * key * i * (i + key));
        data[i] = Binary.RotByteL (data[i], (int)(7 - shift % 7));
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Rune/ArcYK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
