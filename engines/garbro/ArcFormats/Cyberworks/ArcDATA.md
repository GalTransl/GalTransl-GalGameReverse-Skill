# Cyberworks / ArcDATA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `DATA/Csystem` / `GameRes.Formats.Cyberworks.DataOpener` | `data` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `DataOpener.ScanDir` | `var data_file_count = toc_file.View.ReadInt32(toc_offset);` |
| `DataOpener.ScanDir` | `var data_entry_count = toc_file.View.ReadInt32(toc_offset);` |
| `DataOpener.ScanDir` | `entry.UnpackedSize  = toc_file.View.ReadUInt32(toc_offset);` |
| `DataOpener.ScanDir` | `entry.Size          = toc_file.View.ReadUInt32(toc_offset + 4);` |
| `DataOpener.ScanDir` | `entry.Offset        = toc_file.View.ReadUInt32(toc_offset + 8);` |
| `DataOpener.ScanDir` | `var unknow_chunkA_count = toc_file.View.ReadInt32(toc_offset);` |
| `DataOpener.ScanDir` | `var chunkA_extra_count = toc_file.View.ReadInt32(toc_offset);` |
| `DataOpener.ScanDir` | `var unknow_chunkB_count = toc_file.View.ReadInt32(toc_offset);` |
| `DataOpener.ScanDir` | `var chunkB_extra_count = toc_file.View.ReadInt32(toc_offset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Cyberworks.DataScheme

#### 状态与常量

```csharp
public int ExtraHeaderSize ;
```

### GameRes.Formats.Cyberworks.DataOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static DataSchemeMap DefaultScheme = new DataSchemeMap { KnownSchemes = new Dictionary<string, DataScheme>() }
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    var arc_name = Path.GetFileName(file.Name);
    var dir_name = VFS.GetDirectoryName(file.Name);
    var toc_arc_name = VFS.CombinePath(dir_name, "Data00.dat");
    if (!VFS.FileExists(toc_arc_name))
       return null;
    if ("Data00.dat".Equals(arc_name, StringComparison.OrdinalIgnoreCase))
        return null;
    if (!int.TryParse(arc_name.Substring(4, arc_name.IndexOf('.') - 4), out int arc_index))
        return null;
    var scheme = QueryScheme(arc_name);
    var dir = ScanDir(toc_arc_name, arc_index, scheme);
    if (null == dir || 0 == dir.Count)
        return null;

    return new ArcFile(file, this, dir);

}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    if (0 == entry.Size)
        throw new FileSizeException(garStrings.MsgFileIsEmpty);

    Stream input = arc.File.CreateStream(entry.Offset, entry.Size);
    var pent = entry as PackedEntry;
    if (null != pent && pent.IsPacked)
    {
        input = new LzssStream(input);
    }
    return input;
}
```

#### ScanDir

```csharp
List<Entry> ScanDir(string toc_arc_name, int arc_index, DataScheme scheme) {
    var dir = new List<Entry>();
    var toc_offset = 0;

    using (var toc_file = VFS.OpenView(toc_arc_name))
    {
        var data_file_count = toc_file.View.ReadInt32(toc_offset);
        toc_offset += 4;

        if(arc_index >= data_file_count)
           return null;

        for (var i = 0; i < data_file_count; ++i)
        {
            var data_entry_count = toc_file.View.ReadInt32(toc_offset);
            toc_offset += 4;

            for (var j = 0; j < data_entry_count; ++j)
            {
                if (i == arc_index)
                {
                    var entry = new PackedEntry { Name = string.Format("{0:D4}", j) };
                    entry.UnpackedSize  = toc_file.View.ReadUInt32(toc_offset);
                    entry.Size          = toc_file.View.ReadUInt32(toc_offset + 4);
                    entry.Offset        = toc_file.View.ReadUInt32(toc_offset + 8);
                    entry.IsPacked      = (0 != entry.UnpackedSize);
                    entry.Type          = "image";
                    dir.Add(entry);

                }
                toc_offset += (0xC + scheme.ExtraHeaderSize);
            }

            var unknow_chunkA_count = toc_file.View.ReadInt32(toc_offset);
            toc_offset += 4;
            for (var j = 0; j < unknow_chunkA_count; ++j)
            {
                toc_offset += 0xC;
                var chunkA_extra_count = toc_file.View.ReadInt32(toc_offset);
                toc_offset += 4;
                toc_offset += ((chunkA_extra_count-1) * 4);
                toc_offset += (chunkA_extra_count * 0xC);
            }

            var unknow_chunkB_count = toc_file.View.ReadInt32(toc_offset);
            toc_offset += 4;
            if (0 != unknow_chunkB_count)
            {
                toc_offset += 4;
                var chunkB_extra_count = toc_file.View.ReadInt32(toc_offset);
                toc_offset += 4;
                toc_offset += (chunkB_extra_count*8);
            }

        }

    }

    return dir;
}
```

#### QueryScheme

```csharp
DataScheme QueryScheme(string arc_name) {
    var title = FormatCatalog.Instance.LookupGame(arc_name, @"..\*.exe");
    DataScheme scheme = new DataScheme();

    if (!string.IsNullOrEmpty(title) && KnownSchemes.TryGetValue(title, out scheme))
        return scheme;
    var options = Query<DataOptions>(arcStrings.ArcEncryptedNotice);
    if (null != options)
        KnownSchemes.TryGetValue(options.Scheme,out scheme);
    return scheme;

}
```

## 配套算法与外部条件

- [ArcFormats/LzssStream.cs](../LzssStream.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/Cyberworks/ArcDATA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
