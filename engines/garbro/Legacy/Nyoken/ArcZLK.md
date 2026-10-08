# Nyoken / ArcZLK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ZLK` / `GameRes.Formats.Nyoken.ZlkOpener` | `zlk` | `5a4c4b20` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ZlkOpener.TryOpen` | `int version = file.View.ReadInt32 (4);` |
| `ZlkOpener.TryOpen` | `int count = file.View.ReadInt32 (8);` |
| `ZlkOpener.TryOpen` | `uint offset = file.View.ReadUInt32 (index_offset);` |
| `ZlkOpener.TryOpen` | `uint size1  = file.View.ReadUInt32 (index_offset+4);` |
| `ZlkOpener.TryOpen` | `uint size2  = file.View.ReadUInt32 (index_offset+8);` |
| `ZlkOpener.TryOpen` | `byte flags  = file.View.ReadByte (index_offset+12);` |
| `ZlkOpener.TryOpen` | `byte name_length = file.View.ReadByte (index_offset+13);` |
| `ZlkOpener.TryOpen` | `var name = file.View.ReadString (index_offset, name_length);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Nyoken.ZlkOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = file.View.ReadInt32 (4);
    if (version <= 0 || version > 100)
        return null;
    int count = file.View.ReadInt32 (8);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 12;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        uint offset = file.View.ReadUInt32 (index_offset);
        uint size1  = file.View.ReadUInt32 (index_offset+4);
        uint size2  = file.View.ReadUInt32 (index_offset+8);
        byte flags  = file.View.ReadByte (index_offset+12);
        byte name_length = file.View.ReadByte (index_offset+13);
        index_offset += 14;
        var name = file.View.ReadString (index_offset, name_length);
        index_offset += name_length;
        var entry = Create<PackedEntry> (name);
        entry.Offset = offset;
        entry.Size   = size1;
        entry.UnpackedSize = size2;
        entry.IsPacked = flags != 0;
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    var input = arc.File.CreateStream (entry.Offset, entry.Size);
    return new ZLibStream (input, CompressionMode.Decompress);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Nyoken/ArcZLK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
