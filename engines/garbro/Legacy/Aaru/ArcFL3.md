# Aaru / ArcFL3：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `FL3/AARU` / `GameRes.Formats.Aaru.Fl3Opener` | `fl3` | `464c332e` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Fl3Opener.TryOpen` | `if (file.View.ReadByte (4) != '0')` |
| `Fl3Opener.TryOpen` | `uint data_offset  = file.View.ReadUInt16 (8);` |
| `Fl3Opener.TryOpen` | `uint index_size   = file.View.ReadUInt32 (0xA);` |
| `Fl3Opener.TryOpen` | `long index_offset = file.View.ReadUInt32 (0xE);` |
| `Fl3Opener.TryOpen` | `int count         = file.View.ReadInt32 (0x12);` |
| `Fl3Opener.TryOpen` | `ushort key   = file.View.ReadUInt16 (0x16);` |
| `Fl3Opener.TryOpen` | `ushort flags = file.View.ReadUInt16 (0x18);` |
| `Fl3Opener.TryOpen` | `uint size = index.ReadUInt32();` |
| `Fl3Opener.TryOpen` | `int name_length = index.ReadUInt8();` |
| `Fl3Opener.TryOpen` | `var name = index.ReadCString (name_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Aaru.Fl3Opener

继承/接口：`Fl4Opener`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (file.View.ReadByte (4) != '0')
        return null;
    uint data_offset  = file.View.ReadUInt16 (8);
    uint index_size   = file.View.ReadUInt32 (0xA);
    long index_offset = file.View.ReadUInt32 (0xE);
    int count         = file.View.ReadInt32 (0x12);
    if (index_offset + index_size > file.MaxOffset || !IsSaneCount (count))
        return null;
    ushort key   = file.View.ReadUInt16 (0x16);
    ushort flags = file.View.ReadUInt16 (0x18);
    using (var index = file.CreateStream (index_offset, index_size))
    {
        var dir = new List<Entry>();
        for (int i = 0; i < count; ++i)
        {
            uint size = index.ReadUInt32();
            if (uint.MaxValue == size)
                break;
            int name_length = index.ReadUInt8();
            var name = index.ReadCString (name_length);
            var entry = FormatCatalog.Instance.Create<PackedEntry> (name);
            entry.Offset = data_offset;
            entry.Size   = size;
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            data_offset += size;
            dir.Add (entry);
        }
        if (0 == dir.Count)
            return null;
        return new ArcFile (file, this, dir);
    }
}
```

## 配套算法与外部条件

- [Legacy/Aaru/ArcFL4.cs](ArcFL4.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `Legacy/Aaru/ArcFL3.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
