# ArcFormats / MultiFileArchive：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| 辅助算法 | 由调用入口决定 | 不单独识别容器 | 不作支持声明 |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| 辅助算法 | 不独立读取索引；见调用入口和下面的变换步骤 |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.MultiFileArchive

继承/接口：`ArcFile`。

#### 状态与常量

```csharp
IEnumerable<ArcView>  m_parts ;

public IEnumerable<ArcView> Parts {
    get
    {
        yield return File;
        if (m_parts != null)
            foreach (var part in m_parts)
                yield return part;
    }
}

bool m_disposed = false ;
```

#### MultiFileArchive

```csharp
public MultiFileArchive (ArcView arc, ArchiveFormat impl, ICollection<Entry> dir, IEnumerable<ArcView> parts = null)
    : base (arc, impl, dir) {
    m_parts = parts;
}
```

#### OpenStream

```csharp
public Stream OpenStream (Entry entry) {
    Stream input = null;
    try
    {
        long part_offset = 0;
        long entry_start = entry.Offset;
        long entry_end   = entry.Offset + GetEntrySize (entry);
        foreach (var part in Parts)
        {
            long part_end_offset = part_offset + part.MaxOffset;
            if (entry_start < part_end_offset)
            {
                uint part_size = (uint)Math.Min (entry_end - entry_start, part_end_offset - entry_start);
                var entry_part = part.CreateStream (entry_start - part_offset, part_size);
                if (input != null)
                    input = new ConcatStream (input, entry_part);
                else
                    input = entry_part;
                entry_start += part_size;
                if (entry_start >= entry_end)
                    break;
            }
            part_offset = part_end_offset;
        }
        return input ?? Stream.Null;
    }
    catch
    {
        if (input != null)
            input.Dispose();
        throw;
    }
}
```

#### GetEntrySize

```csharp
protected virtual uint GetEntrySize (Entry entry) {
    return entry.Size;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/MultiFileArchive.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
