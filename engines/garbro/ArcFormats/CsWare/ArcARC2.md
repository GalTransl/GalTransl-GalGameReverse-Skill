# CsWare / ArcARC2：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/ARC2` / `GameRes.Formats.CsWare.Arc2Opener` | `dat` | `61726332` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `Arc2Opener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `Arc2Opener.TryOpen` | `uint index_offset = file.View.ReadUInt32 (8);` |
| `Arc2Opener.TryOpen` | `var name = file.View.ReadString (index_offset, 0x10);` |
| `Arc2Opener.TryOpen` | `entry.Offset = file.View.ReadUInt32 (index_offset+0x10);` |
| `Arc2Opener.TryOpen` | `entry.Size   = file.View.ReadUInt32 (index_offset+0x14);` |
| `Arc2Opener.TryOpen` | `entry.Key1   = file.View.ReadUInt32 (index_offset+0x18);` |
| `Arc2Opener.TryOpen` | `entry.Key2   = file.View.ReadUInt32 (index_offset+0x1C);` |
| `Arc2Opener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset) - (entry.Key1 + entry.Key2);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.CsWare.Arc2Entry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public uint Key1 ;

public uint Key2 ;
```

### GameRes.Formats.CsWare.Arc2Opener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;
    uint index_offset = file.View.ReadUInt32 (8);
    if (index_offset >= file.MaxOffset)
        return null;
    var names = new HashSet<string>();
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, 0x10);
        if (names.Add (name))
        {
            var entry = Create<Arc2Entry> (name);
            entry.Offset = file.View.ReadUInt32 (index_offset+0x10);
            entry.Size   = file.View.ReadUInt32 (index_offset+0x14);
            if (!entry.CheckPlacement (file.MaxOffset))
                return null;
            entry.Key1   = file.View.ReadUInt32 (index_offset+0x18);
            entry.Key2   = file.View.ReadUInt32 (index_offset+0x1C);
            dir.Add (entry);
        }
        index_offset += 0x20;
    }
    foreach (Arc2Entry entry in dir)
    {
        uint signature = file.View.ReadUInt32 (entry.Offset) - (entry.Key1 + entry.Key2);
        entry.ChangeType (AutoEntry.DetectFileType (signature));
    }
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var a2ent = entry as Arc2Entry;
    if (null == a2ent || 0 == (a2ent.Key1 | a2ent.Key2))
        return base.OpenEntry (arc, entry);
    uint length = (entry.Size + 3) & ~3u;
    var data = new byte[length];
    arc.File.View.Read (entry.Offset, data, 0, entry.Size);
    uint key1 = a2ent.Key1;
    uint key2 = a2ent.Key2;
    unsafe
    {
        fixed (byte* data8 = data)
        {
            uint* data32 = (uint*)data8;
            for (uint i = 0; i < length; i += 4)
            {
                uint key_sum = key1 + key2;
                *data32++ -= key_sum;
                key1 = key2;
                key2 = key_sum;
            }
        }
    }
    return new BinMemoryStream (data, 0, (int)entry.Size, entry.Name);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/CsWare/ArcARC2.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
