# Fog / ArcDAT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DAT/FOG` / `GameRes.Formats.Fog.DatOpener` | `dat` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DatOpener.TryOpen` | `uint name_length = Binary.BigEndian(reader.ReadUInt32());` |
| `DatOpener.TryOpen` | `string name = Binary.GetCString(reader.ReadBytes((int)name_length), 0);` |
| `DatOpener.TryOpen` | `uint part = Binary.BigEndian(reader.ReadUInt32());` |
| `DatOpener.TryOpen` | `reader.ReadUInt32();` |
| `DatOpener.TryOpen` | `entry.Offset = Binary.BigEndian(reader.ReadUInt32());` |
| `DatOpener.TryOpen` | `entry.Size = Binary.BigEndian(reader.ReadUInt32());` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Fog.DatEntry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public string FileName ;
```

### GameRes.Formats.Fog.DatOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    var base_name = Path.GetFileNameWithoutExtension(file.Name);
    bool multipart = base_name.Contains("_");
    if (multipart)
        base_name = base_name.Split('_')[0];
    var index_file_name = base_name + "File.dat";
    if (!File.Exists(index_file_name))
        return null;

    var index = File.ReadAllBytes(index_file_name);
    var transformer = new NotTransform();
    transformer.TransformBlock(index, 0, index.Length, index, 0);

    using (var mem = new MemoryStream(index))
    using (var reader = new BinaryReader(mem)) {
        var dir = new List<Entry>();

        while (mem.Position < mem.Length) {
            uint name_length = Binary.BigEndian(reader.ReadUInt32());
            string name = Binary.GetCString(reader.ReadBytes((int)name_length), 0);
            var entry = Create<DatEntry>(name);
            if (multipart) {
                uint part = Binary.BigEndian(reader.ReadUInt32());
                entry.FileName = string.Format("{0}_{1:00}.dat", base_name, part);
                if (!File.Exists(entry.FileName))
                    return null;
            }
            else {
                entry.FileName = file.Name;
            }
            reader.ReadUInt32();
            entry.Offset = Binary.BigEndian(reader.ReadUInt32());
            reader.ReadUInt32();
            entry.Size = Binary.BigEndian(reader.ReadUInt32());
            dir.Add(entry);
        }

        return new ArcFile(file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var dent = entry as DatEntry;
    using (var data_file = new ArcView(dent.FileName)) {
        var input = data_file.CreateStream(dent.Offset, dent.Size);
        return new XoredStream(input, 0xFF);
    }
}
```

## 配套算法与外部条件

- [ArcFormats/CommonStreams.cs](../CommonStreams.md)：本页引用的随包算法资料。
- [ArcFormats/SimpleEncryption.cs](../SimpleEncryption.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Fog/ArcDAT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
