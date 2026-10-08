# KiriKiri / YuzCrypt：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `SenrenCxCrypt.ReadYuzNames` | `uint entry_signature = input.ReadUInt32();` |
| `SenrenCxCrypt.ReadYuzNames` | `long entry_size = input.ReadInt64();` |
| `SenrenCxCrypt.ReadYuzNames` | `uint hash = input.ReadUInt32();` |
| `SenrenCxCrypt.ReadYuzNames` | `int name_size = input.ReadInt16();` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.KiriKiri.SenrenCxCrypt

继承/接口：`CxEncryption`。

#### 状态与常量

```csharp
public virtual string NamesSectionId { get { return "sen:"; } }
```

#### ReadYuzNames

```csharp
internal virtual void ReadYuzNames (byte[] yuz, FilenameMap filename_map) {
    using (var ystream = new MemoryStream (yuz))
    using (var zstream = ZLibCompressor.DeCompress (ystream))
    using (var input = new BinaryReader (zstream, Encoding.Unicode))
    {
        long dir_offset = 0;
        while (-1 != input.PeekChar())
        {
            uint entry_signature = input.ReadUInt32();
            long entry_size = input.ReadInt64();
            if (entry_size < 0)
                return;
            dir_offset += 12 + entry_size;
            uint hash = input.ReadUInt32();
            int name_size = input.ReadInt16();
            if (name_size > 0)
            {
                entry_size -= 6;
                if (name_size * 2 <= entry_size)
                {
                    var filename = new string (input.ReadChars (name_size));
                    filename_map.Add (hash, filename);
                }
            }
            input.BaseStream.Position = dir_offset;
        }
        filename_map.AddShortcut ("$", "startup.tjs");
    }
}
```

## 配套算法与外部条件

- [ArcFormats/KiriKiri/ArcXP3.cs](ArcXP3.md)：本页引用的随包算法资料。
- [ArcFormats/KiriKiri/KiriKiriCx.cs](KiriKiriCx.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/KiriKiri/YuzCrypt.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
