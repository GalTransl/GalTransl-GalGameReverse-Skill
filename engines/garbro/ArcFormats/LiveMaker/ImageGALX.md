# LiveMaker / ImageGALX：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

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

### GameRes.Formats.LiveMaker.GalXMetaData

继承/接口：`GalMetaData`。

#### 状态与常量

```csharp
public XmlNode  FrameXml ;
```

### GameRes.Formats.LiveMaker.GalXFormat

继承/接口：`ImageFormat`。

#### 状态与常量

```csharp
static readonly Regex FrameRe = new Regex (@"<Frame [^>]+>") ;
```

#### ReadXml

```csharp
internal XmlDocument ReadXml (Stream input) {

    using (var reader = new StreamReader (input))
    {
        var text = reader.ReadToEnd();
        text = FrameRe.Replace (text, "<Frame>");
        var xml = new XmlDocument();
        xml.LoadXml (text);
        return xml;
    }
}
```

## 配套算法与外部条件

- [ArcFormats/LiveMaker/ImageGAL.cs](ImageGAL.md)：本页引用的随包算法资料。

## 出处与许可

来源文件标识 `ArcFormats/LiveMaker/ImageGALX.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
