# AdvRun / ArcARD：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `ARD` / `GameRes.Formats.AdvRun.ArdOpener` | `ard` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `ArdOpener.TryOpen` | `if (!file.View.AsciiEqual(4, "ARD0"))` |
| `ArdOpener.TryOpen` | `int count = file.View.ReadInt32(8);` |
| `ArdOpener.TryOpen` | `var name = file.View.ReadString(index_offset + 0xc, 0x21, Encodings.cp932);` |
| `ArdOpener.TryOpen` | `Offset = file.View.ReadUInt32(index_offset),` |
| `ArdOpener.TryOpen` | `file.View.ReadUInt32(index_offset + 4),` |
| `ArdOpener.TryOpen` | `file.View.ReadUInt32(index_offset + 8)),` |
| `ArdOpener.OpenEntry` | `var data = ard.File.View.ReadBytes (entry.Offset, entry.Size);` |
| `ArdOpener.FindKey` | `var data = file.View.ReadBytes(0, (uint)file.MaxOffset);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.AdvRun.ArdArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
private string m_key ;

public string Key { get { return m_key; } }
```

#### ArdArchive

```csharp
public ArdArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, string key)
    : base (arc, impl, dir) {
    m_key = key;
}
```

### GameRes.Formats.AdvRun.ArdOpener

继承/接口：`ArchiveFormat`。

#### ArdOpener

```csharp
public ArdOpener() {
    Extensions = new string[] { "ard" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    if (!file.View.AsciiEqual(4, "ARD0"))
        return null;

    var inf_name = VFS.ChangeFileName(file.Name, "Game.Inf");
    if (!VFS.FileExists(inf_name))
        return null;

    using (var inf = VFS.OpenView(inf_name)) {
        var key = FindKey(inf);
        if (key == null)
            return null;

        int count = file.View.ReadInt32(8);
        if (!IsSaneCount(count))
            return null;

        var dir = new List<Entry>(count);
        uint index_offset = 0x100;
        for (int i = 0; i < count; i++) {
            var name = file.View.ReadString(index_offset + 0xc, 0x21, Encodings.cp932);
            var entry = new PackedEntry {
                Name = name,
                Offset = file.View.ReadUInt32(index_offset),
                Size = Math.Min(
                        file.View.ReadUInt32(index_offset + 4),
                        file.View.ReadUInt32(index_offset + 8)),
            };

            name = name.ToLower();
            if (name.EndsWith(".snf")) entry.Type = "script";
            else if (name.EndsWith(".piz")) entry.Type = "image";
            else entry.Type = FormatCatalog.Instance.GetTypeFromName(name);

            if (!entry.CheckPlacement(file.MaxOffset))
                return null;
            index_offset += 0x2d;
            dir.Add(entry);
        }

        return new ArdArchive(file, this, dir, key);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var ard = arc as ArdArchive;
    var data = ard.File.View.ReadBytes (entry.Offset, entry.Size);
    if (entry.Name.ToLower().EndsWith(".snf")) {
        XorDecrypt(data, ard.Key);
        var input = new MemoryStream(data, 4, (int)(entry.Size - 4));
        return new ZLibStream(input, CompressionMode.Decompress);
    }
    return new BinMemoryStream(data);
}
```

#### FindKey

```csharp
string FindKey(ArcView file) {
    var data = file.View.ReadBytes(0, (uint)file.MaxOffset);
    XorDecrypt(data, "1#jk@oih%6");
    using (var input = new MemoryStream(data, 4, data.Length - 4))
    using (var unpacked = new ZLibStream(input, CompressionMode.Decompress))
    using (var output = new MemoryStream()) {
        unpacked.CopyTo(output);
        var conf = Binary.GetCString(output.ToArray(), 0);
        var match = Regex.Match(conf, "^@gcode\\(\"(.*).\"\\)", RegexOptions.Multiline);
        if (match.Success)
            return match.Groups[1].Value;
        else
            return null;
    }
}
```

#### XorDecrypt

```csharp
void XorDecrypt(byte[] buffer, string key) {
    var k = Encodings.cp932.GetBytes(key);
    for (int i = 0; i < buffer.Length; i++)
        buffer[i] ^= k[i % k.Length];
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/AdvRun/ArcARD.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
