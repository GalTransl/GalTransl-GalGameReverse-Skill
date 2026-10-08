# NScripter / ArcSAR：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `SAR` / `GameRes.Formats.NScripter.SarOpener` | `sar` | 无固定签名或来源表达式未解析 | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SarOpener.TryOpen` | `int num_of_files = Binary.BigEndian (file.View.ReadInt16 (0));` |
| `SarOpener.TryOpen` | `uint base_offset = Binary.BigEndian (file.View.ReadUInt32 (2));` |
| `SarOpener.TryOpen` | `entry.Offset = Binary.BigEndian (file.View.ReadUInt32 (cur_offset)) + (long)base_offset;` |
| `SarOpener.TryOpen` | `entry.Size   = Binary.BigEndian (file.View.ReadUInt32 (cur_offset+4));` |
| `SarOpener.ReadName` | `byte b = file.View.ReadByte (offset+name_len);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.NScripter.SarOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    int num_of_files = Binary.BigEndian (file.View.ReadInt16 (0));
    if (num_of_files <= 0)
        return null;
    uint base_offset = Binary.BigEndian (file.View.ReadUInt32 (2));
    if (base_offset >= file.MaxOffset || base_offset < 10 * (uint)num_of_files)
        return null;

    uint cur_offset = 6;
    var dir = new List<Entry>();
    for (int i = 0; i < num_of_files; ++i)
    {
        if (base_offset - cur_offset < 10)
            return null;
        int name_len;
        byte[] name_buffer = ReadName (file, cur_offset, base_offset-cur_offset, out name_len);
        if (0 == name_len || base_offset-cur_offset == name_len)
            return null;
        cur_offset += (uint)(name_len + 1);
        if (base_offset - cur_offset < 8)
            return null;

        string name = Encodings.cp932.GetString (name_buffer, 0, name_len);
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = Binary.BigEndian (file.View.ReadUInt32 (cur_offset)) + (long)base_offset;
        entry.Size   = Binary.BigEndian (file.View.ReadUInt32 (cur_offset+4));
        if (!entry.CheckPlacement (file.MaxOffset))
            return null;

        cur_offset += 8;
        dir.Add (entry);
    }
    return new ArcFile (file, this, dir);
}
```

#### ReadName

```csharp
protected static byte[] ReadName (ArcView file, uint offset, uint limit, out int name_len) {
    byte[] name_buffer = new byte[40];
    for (name_len = 0; name_len < limit; ++name_len)
    {
        byte b = file.View.ReadByte (offset+name_len);
        if (0 == b)
            break;
        if (name_buffer.Length == name_len)
        {
            Array.Resize (ref name_buffer, checked(name_len/2*3));
        }
        name_buffer[name_len] = b;
    }
    return name_buffer;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/NScripter/ArcSAR.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
