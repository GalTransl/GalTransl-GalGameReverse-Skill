# FC01 / ArcBDT：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `BDT` / `GameRes.Formats.FC01.BdtOpener` | `bdt` | `5041434b` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `BdtOpener.TryOpen` | `uint signature = file.View.ReadUInt32 (0);` |
| `BdtOpener.TryOpen` | `int count = file.View.ReadInt32 (4);` |
| `BdtOpener.TryOpen` | `int entry_size = file.View.ReadInt32 (8);` |
| `BdtOpener.BogusMediaArchive` | `else if (AudioFormat.Wav.Signature == signature && file.View.AsciiEqual (8, "AVI "))` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.FC01.BdtOpener

继承/接口：`PakOpener`。

#### BdtOpener

```csharp
public BdtOpener () {
    Signatures = new[] { 0x4B434150u, 0u };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    uint signature = file.View.ReadUInt32 (0);
    if (signature != this.Signature)
        return BogusMediaArchive (file, signature);
    var arc_name = Path.GetFileNameWithoutExtension (file.Name).ToLowerInvariant();
    if (!arc_name.StartsWith ("dt0"))
        return null;

    uint index_pos = 12;
    int count = file.View.ReadInt32 (4);
    if (!IsSaneCount (count) || file.MaxOffset <= index_pos)
        return null;
    int entry_size = file.View.ReadInt32 (8);

    string arc_num_str = arc_name.Substring (3);
    int arc_num = int.Parse (arc_num_str, NumberStyles.HexNumber);
    var dir = ReadVomIndex (file, arc_num, count, entry_size);
    if (null == dir)
        return null;
    var arc_key = GetKey (arc_num);
    return new AgsiArchive (file, this, dir, arc_key);
}
```

#### ReadVomIndex

```csharp
List<Entry> ReadVomIndex (ArcView file, int arc_num, int count, int record_size) {
    if (4 == arc_num)
    {
        var reader = new IndexReader (file, count, record_size);
        return reader.ReadIndex();
    }
    var dt4name = VFS.ChangeFileName (file.Name, "dt004.bdt");
    using (var dt4file = VFS.OpenView (dt4name))
    {
        var dt4arc = TryOpen (dt4file);
        if (null == dt4arc)
            return null;
        using (dt4arc)
        {
            int vom_idx = arc_num;
            if (arc_num > 4)
                --vom_idx;
            var voms = string.Format ("vom{0:D3}.dat", vom_idx);
            var vom_entry = dt4arc.Dir.First (e => e.Name == voms);
            using (var input = dt4arc.OpenEntry (vom_entry))
            using (var index = BinaryStream.FromStream (input, vom_entry.Name))
            {
                var reader = new IndexReader (file, count, record_size);
                return reader.ReadIndex (index);
            }
        }
    }
}
```

#### BogusMediaArchive

```csharp
ArcFile BogusMediaArchive (ArcView file, uint signature) {
    if (!file.Name.HasExtension (".bdt"))
        return null;
    string ext = null;
    string type = "";
    if (OggAudio.Instance.Signature == signature)
    {
        ext = ".ogg";
        type = "audio";
    }
    else if (AudioFormat.Wav.Signature == signature && file.View.AsciiEqual (8, "AVI "))
    {
        ext = ".avi";
    }
    if (null == ext)
        return null;
    var name = Path.GetFileNameWithoutExtension (file.Name);
    var dir = new List<Entry> {
        new Entry {
            Name = name + ext,
            Type = type,
            Offset = 0,
            Size = (uint)file.MaxOffset
        }
    };
    return new ArcFile (file, this, dir);
}
```

#### GetKey

```csharp
byte[] GetKey (int index) {
    int src = index * 8;
    if (src + 8 > KeyOffsetTable.Length)
        throw new ArgumentException ("Invalid AGSI key index.");
    var key = new byte[8];
    key[0] = KeySource[KeyOffsetTable[src++]];
    key[1] = KeySource[KeyOffsetTable[src++]];
    key[2] = KeySource[KeyOffsetTable[src++]];
    key[3] = KeySource[KeyOffsetTable[src++] + 480];
    key[4] = KeySource[KeyOffsetTable[src++] + 480];
    key[5] = KeySource[KeyOffsetTable[src++] + 480];
    key[6] = KeySource[KeyOffsetTable[src++] + 480];
    key[7] = KeySource[KeyOffsetTable[src++] + 480];
    return key;
}
```

## 配套算法与外部条件

- [ArcFormats/AudioOGG.cs](../AudioOGG.md)：本页引用的随包算法资料。
- [ArcFormats/FC01/ArcPAK.cs](ArcPAK.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/FC01/ArcBDT.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
