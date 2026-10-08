# Leaf / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/KCAP` / `GameRes.Formats.Leaf.KcapOpener` | `pak` | `4b434150` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `KcapOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `KcapOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (0x20);` |
| `KcapOpener.TryOpen` | `first_offset = file.View.ReadUInt32 (0x24);` |
| `KcapOpener.TryOpen` | `count = file.View.ReadInt32 (8);` |
| `KcapOpener.TryOpen` | `first_offset = file.View.ReadUInt32 (0x28);` |
| `KcapOpener.TryOpen` | `count = file.View.ReadInt32 (12);` |
| `KcapOpener.TryOpen` | `first_offset = file.View.ReadUInt32 (0x34);` |
| `KcapOpener.OpenEntry` | `pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Leaf.KcapOpener

继承/接口：`ArchiveFormat`。

#### KcapOpener

```csharp
public KcapOpener () {
    ContainedFormats = new[] { "TGA", "BJR", "BMP", "OGG", "WAV", "AMP/LEAF", "SCR" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int version = -1;
    int count = file.View.ReadInt32 (4);
    uint index_offset = 8;
    uint first_offset = file.View.ReadUInt32 (0x20);
    if (IsSaneCount (count))
    {
        if (count * 0x20 + 8 == first_offset)
        {
            version = 0;
        }
        else
        {
            first_offset = file.View.ReadUInt32 (0x24);
            if (count * 0x24 + 8 == first_offset)
                version = 1;
        }
    }
    if (version < 0)
    {
        count = file.View.ReadInt32 (8);
        first_offset = file.View.ReadUInt32 (0x28);
        if (IsSaneCount (count) && count * 0x24 + 0xC == first_offset)
        {
            version = 1;
            index_offset = 0xC;
        }
        else
        {
            count = file.View.ReadInt32 (12);
            first_offset = file.View.ReadUInt32 (0x34);
            if (IsSaneCount (count) && count * 0x2C + 0x10 == first_offset)
            {
                version = 2;
                index_offset = 0x10;
            }
        }
    }
    List<Entry> dir = null;
    switch (version)
    {
    case 0: dir = ReadIndex<EntryDefV0> (file, count, index_offset); break;
    case 1: dir = ReadIndex<EntryDefV1> (file, count, index_offset); break;
    case 2: dir = ReadIndex<EntryDefV2> (file, count, index_offset); break;
    default: return null;
    }
    if (null == dir)
        return null;
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    var pent = entry as PackedEntry;
    if (null == pent || !pent.IsPacked)
        return base.OpenEntry (arc, entry);
    if (0 == pent.UnpackedSize)
        pent.UnpackedSize = arc.File.View.ReadUInt32 (entry.Offset+4);
    var input = arc.File.CreateStream (entry.Offset+8, entry.Size-8);
    return new LzssStream (input);
}
```

### GameRes.Formats.Leaf.EntryDefV0

继承/接口：`IEntryDefinition`。

#### 状态与常量

```csharp
uint    _offset ;

uint    _size ;

public string   Name { get { return _name; } }

public long   Offset { get { return _offset; } }

public uint     Size { get { return _size; } }

public bool IsPacked { get { return true; } }
```

#### CString

```csharp
[CString(Length = 0x18)]
string  _name ;
```

### GameRes.Formats.Leaf.EntryDefV1

继承/接口：`IEntryDefinition`。

#### 状态与常量

```csharp
int     _is_packed ;

uint    _offset ;

uint    _size ;

public string   Name { get { return _name; } }

public long   Offset { get { return _offset; } }

public uint     Size { get { return _size; } }

public bool IsPacked { get { return _is_packed != 0; } }
```

#### CString

```csharp
[CString(Length = 0x18)]
string  _name ;
```

### GameRes.Formats.Leaf.EntryDefV2

继承/接口：`IEntryDefinition`。

#### 状态与常量

```csharp
int     _is_packed ;

uint    _crc ;

uint    _unpacked_size ;

uint    _offset ;

uint    _size ;

public string   Name { get { return _name; } }

public long   Offset { get { return _offset; } }

public uint     Size { get { return _size; } }

public bool IsPacked { get { return _is_packed != 0; } }
```

#### CString

```csharp
[CString(Length = 0x18)]
string  _name ;
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Leaf/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
