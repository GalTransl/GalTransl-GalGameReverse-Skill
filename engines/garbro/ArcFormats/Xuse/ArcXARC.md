# Xuse / ArcXARC：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `XARC/XUSE` / `GameRes.Formats.Xuse.XarcOpener` | `arc` | `58415243` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `XarcOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `XarcOpener.TryOpen` | `uint first_offset = file.View.ReadUInt32 (index_offset);` |
| `XarcOpener.TryOpen` | `var entry = new Entry { Offset = file.View.ReadUInt32 (index_offset) };` |
| `XarcOpener.TryOpen` | `if (!file.View.AsciiEqual (entry.Offset, "DATA"))` |
| `XarcOpener.TryOpen` | `uint name_length = file.View.ReadUInt16 (entry.Offset+0x18);` |
| `XarcOpener.TryOpen` | `entry.Size = file.View.ReadUInt32 (entry.Offset+0x1C);` |
| `XarcOpener.TryOpen` | `var name = file.View.ReadBytes (entry.Offset+0x20, name_length);` |
| `XarcOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (entry.Offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Xuse.XarcOpener

继承/接口：`ArchiveFormat`。

#### XarcOpener

```csharp
public XarcOpener () {
    Extensions = new string[] { "arc" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count))
        return null;

    uint index_offset = 8;
    uint first_offset = file.View.ReadUInt32 (index_offset);
    if ((uint)count*4 + 10 != first_offset)
        return null;
    var base_name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> (count);
    for (int i = 0; i < count; ++i)
    {
        var entry = new Entry { Offset = file.View.ReadUInt32 (index_offset) };
        dir.Add (entry);
        index_offset += 4;
    }
    foreach (var entry in dir)
    {
        if (!file.View.AsciiEqual (entry.Offset, "DATA"))
            return null;
        uint name_length = file.View.ReadUInt16 (entry.Offset+0x18);
        entry.Size = file.View.ReadUInt32 (entry.Offset+0x1C);
        var name = file.View.ReadBytes (entry.Offset+0x20, name_length);
        entry.Name = DecryptName (name);
        entry.Offset += 0x22 + name_length;
        uint signature = file.View.ReadUInt32 (entry.Offset);
        var res = AutoEntry.DetectFileType (signature);
        if (res != null)
            entry.Type = res.Type;
    }
    return new ArcFile (file, this, dir);
}
```

#### DecryptName

```csharp
string DecryptName (byte[] name) {
    for (int i = 0; i < name.Length; ++i)
    {
        name[i] = Binary.RotByteL (name[i], 4);
    }
    return Encodings.cp932.GetString (name);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Xuse/ArcXARC.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
