# Broccoli / ArcP00：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `P00` / `GameRes.Formats.Broccoli.P00Opener` | `p00` | 无固定签名或来源表达式未解析 | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `P00Opener.TryOpen` | `if (!index_file.View.AsciiEqual(0, "IPF "))` |
| `P00Opener.TryOpen` | `int count = index_file.View.ReadInt32(4);` |
| `P00Opener.TryOpen` | `uint hash = index_file.View.ReadUInt32(index_offset);` |
| `P00Opener.TryOpen` | `entry.Offset = index_file.View.ReadUInt32(index_offset + 4);` |
| `P00Opener.TryOpen` | `entry.Size   = index_file.View.ReadUInt32(index_offset + 8);` |
| `P00Opener.OpenEntry` | `if (input.ReadUInt16() == 0x305A) {` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.Broccoli.P00Entry

继承/接口：`Entry`。

#### 状态与常量

```csharp
public string FileName ;
```

### GameRes.Formats.Broccoli.P00Opener

继承/接口：`ArchiveFormat`。

#### P00Opener

```csharp
public P00Opener() {
    Extensions = new string[] { "p00" };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen(ArcView file) {
    var index_file_name = Path.ChangeExtension(file.Name, "pak");
    if (!VFS.FileExists(index_file_name))
        return null;
    using (var index_file = VFS.OpenView(index_file_name)) {
        if (!index_file.View.AsciiEqual(0, "IPF "))
            return null;

        int count = index_file.View.ReadInt32(4);
        if (!IsSaneCount(count))
            return null;

        long index_offset = 8;
        var dir = new List<Entry>(count);
        for (int i = 0; i < count; i++) {
            uint hash = index_file.View.ReadUInt32(index_offset);
            string name = hash.ToString("X8");
            var entry = Create<P00Entry>(name);
            entry.Offset = index_file.View.ReadUInt32(index_offset + 4);
            entry.Size   = index_file.View.ReadUInt32(index_offset + 8);
            var data_file_name = Path.ChangeExtension(file.Name, string.Format("p{0:00}", entry.Offset >> 28));
            if (!VFS.FileExists(data_file_name))
                return null;
            entry.FileName = data_file_name;
            dir.Add(entry);
            index_offset += 12;
        }

        return new ArcFile(file, this, dir);
    }
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry(ArcFile arc, Entry entry) {
    var pent = entry as P00Entry;
    using (var data_file = new ArcView(pent.FileName)) {
        var input = data_file.CreateStream(pent.Offset & 0xFFFFFFF, pent.Size);
        if (input.ReadUInt16() == 0x305A) {
            input.Seek(10, SeekOrigin.Begin);
            return new DeflateStream(input, CompressionMode.Decompress);
        }
        else {
            input.Seek(0, SeekOrigin.Begin);
            return input;
        }
    }
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/Broccoli/ArcP00.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
