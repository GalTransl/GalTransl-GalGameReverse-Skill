# System21 / ArcPAK：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `PAK/SYSTEM21` / `GameRes.Formats.System21.PakOpener` | `pak` | `8fad8f97`, `89f58a79` | `False` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `PakOpener.TryOpen` | `bool new_version = file.View.ReadUInt32 (0) == 0x798AF589u;` |
| `PakOpener.TryOpen` | `uint data_offset = file.View.ReadUInt32 (4);` |
| `PakOpener.ReadIndex` | `var name = file.View.ReadString (index_offset, name_size);` |
| `PakOpener.ReadIndex` | `entry.Size = file.View.ReadUInt32 (index_offset + name_size);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.System21.PakOpener

继承/接口：`ArchiveFormat`。

#### 状态与常量

```csharp
static readonly byte[] NameSizes = { 0x14, 0x34, 0x64 }
```

#### PakOpener

```csharp
public PakOpener () {
    Signatures = new uint[] { 0x978FAD8F, 0x798AF589 };
}
```

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    bool new_version = file.View.ReadUInt32 (0) == 0x798AF589u;
    uint data_offset = file.View.ReadUInt32 (4);
    int n = new_version ? 0 : 2;
    uint index_size = data_offset - 12;
    var dir = new List<Entry>();
    for (; n < NameSizes.Length; ++n)
    {
        uint name_size = NameSizes[n];
        if (index_size % (name_size + 4) != 0)
            continue;
        int count = (int)(index_size / (name_size + 4));
        if (!IsSaneCount (count))
            continue;

        dir.Clear();
        if (ReadIndex (file, count, data_offset, dir, name_size))
            return new ArcFile (file, this, dir);
    }
    return null;
}
```

#### ReadIndex

```csharp
bool ReadIndex (ArcView file, int count, uint data_offset, List<Entry> dir, uint name_size) {
    uint index_offset = 12;
    for (int i = 0; i < count; ++i)
    {
        var name = file.View.ReadString (index_offset, name_size);
        if (string.IsNullOrEmpty (name))
            return false;
        var entry = FormatCatalog.Instance.Create<Entry> (name);
        entry.Offset = data_offset;
        entry.Size = file.View.ReadUInt32 (index_offset + name_size);
        if (!entry.CheckPlacement (file.MaxOffset))
            return false;
        dir.Add (entry);
        index_offset += name_size + 4;
        data_offset += entry.Size;
    }
    return true;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `Legacy/System21/ArcPAK.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
