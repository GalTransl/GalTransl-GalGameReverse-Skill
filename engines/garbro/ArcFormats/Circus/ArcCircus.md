# Circus / ArcCircus：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/CIRCUS` / `GameRes.Formats.Circus.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpenFromHeader` | `int count = file.View.ReadInt32(0);` |
| `DatOpener.TryOpenFromFooter` | `int count = file.View.ReadInt32(file.MaxOffset - 4);` |
| `DatOpener.TryOpenFromFooter` | `var dir = ReadIndexV2(file, count, file.View.ReadInt32(file.MaxOffset - 0x8));` |
| `DatOpener.ReadIndexV1` | `uint next_offset = file.View.ReadUInt32 (index_offset+name_length);` |
| `DatOpener.ReadIndexV1` | `uint first_size    = file.View.ReadUInt32 (index_offset+name_length-4);` |
| `DatOpener.ReadIndexV1` | `uint second_offset = file.View.ReadUInt32 (index_offset+name_length*2+4);` |
| `DatOpener.ReadIndexV1` | `string name = file.View.ReadString (index_offset, (uint)name_length);` |
| `DatOpener.ReadIndexV1` | `next_offset = file.View.ReadUInt32 (index_offset+4+name_length);` |
| `DatOpener.ReadIndexV2` | `int name_length = file.View.ReadByte(index_offset);` |
| `DatOpener.ReadIndexV2` | `string name = file.View.ReadString(index_offset, (uint)name_length);` |
| `DatOpener.ReadIndexV2` | `uint entry_size = file.View.ReadUInt32(index_offset);` |
| `DatOpener.ReadIndexV2` | `long entry_offset = file.View.ReadInt32(index_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Circus.DatOpener

继承/接口：`ArchiveFormat`。

#### DatOpener

```csharp
public DatOpener () {
    Extensions = new string[] { "dat" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    var arcFile = TryOpenFromHeader(file);
    if (null != arcFile)
    {
        return arcFile;
    }

    arcFile = TryOpenFromFooter(file);

    return arcFile;
}
```

#### TryOpenFromHeader

```csharp
public ArcFile TryOpenFromHeader(ArcView file) {
    int count = file.View.ReadInt32(0);
    if (count <= 1 || count > 0xfffff)
        return null;
    var dir = ReadIndexV1(file, count, 0x24);
    if (null == dir)
        dir = ReadIndexV1(file, count, 0x30);
    if (null == dir)
        dir = ReadIndexV1(file, count, 0x3C);
    if (null == dir)
        return null;
    return new ArcFile(file, this, dir);
}
```

#### TryOpenFromFooter

```csharp
public ArcFile TryOpenFromFooter(ArcView file) {
    int count = file.View.ReadInt32(file.MaxOffset - 4);
    if(count <= 1 || count > 0xfffff)
    {
        return null;
    }

   var dir = ReadIndexV2(file, count, file.View.ReadInt32(file.MaxOffset - 0x8));

   return new ArcFile(file, this, dir);
}
```

#### ReadIndexV1

```csharp
private List<Entry> ReadIndexV1 (ArcView file, int count, int name_length) {
    long index_offset = 4;
    uint index_size = (uint)((name_length + 4) * count);
    if (index_size > file.View.Reserve (index_offset, index_size))
        return null;
    --count;
    uint next_offset = file.View.ReadUInt32 (index_offset+name_length);
    if (next_offset < 4+index_size)
        return null;
    uint first_size    = file.View.ReadUInt32 (index_offset+name_length-4);
    uint second_offset = file.View.ReadUInt32 (index_offset+name_length*2+4);
    if (second_offset - next_offset == first_size)
        return null;
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        string name = file.View.ReadString (index_offset, (uint)name_length);
        if (0 == name.Length)
            return null;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        index_offset += name_length;
        uint offset = next_offset;
        if (i+1 == count)
            next_offset = (uint)file.MaxOffset;
        else
            next_offset = file.View.ReadUInt32 (index_offset+4+name_length);
        if (next_offset < offset)
            return null;
        entry.Size = next_offset - offset;
        entry.Offset = offset;
        if (offset < index_size || !entry.CheckPlacement (file.MaxOffset))
            return null;
        dir.Add (entry);
        index_offset += 4;
    }
    return dir;
}
```

#### ReadIndexV2

```csharp
private List<Entry> ReadIndexV2(ArcView file, int count, long start_offset) {
    uint max_index_size = (uint)(count * 0x4C);
    long index_offset = start_offset;
    var dir = new List<Entry> (count);

    file.View.Reserve(start_offset, max_index_size);

    for (int i = 0; i < count; i++)
    {
        int name_length = file.View.ReadByte(index_offset);
        index_offset++;

        string name = file.View.ReadString(index_offset, (uint)name_length);
        index_offset += name_length;

        uint entry_size = file.View.ReadUInt32(index_offset);
        index_offset += 8;

        long entry_offset = file.View.ReadInt32(index_offset);
        index_offset += 4;

        var entry = FormatCatalog.Instance.Create<Entry>(name);
        entry.Size = entry_size;
        entry.Offset = entry_offset;
        dir.Add(entry);
    }

    return dir;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Circus/ArcCircus.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
