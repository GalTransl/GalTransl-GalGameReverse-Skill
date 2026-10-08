# Lzma / LzmaBase：归档读取与解码

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

### SevenZip.Compression.LZMA.Base

#### 状态与常量

```csharp
public const uint kNumRepDistances = 4 ;

public const uint kNumStates = 12 ;

public const int kNumPosSlotBits = 6 ;

public const int kDicLogSizeMin = 0 ;

public const int kNumLenToPosStatesBits = 2 ;

public const uint kNumLenToPosStates = 1 << kNumLenToPosStatesBits ;

public const uint kMatchMinLen = 2 ;

public const int kNumAlignBits = 4 ;

public const uint kAlignTableSize = 1 << kNumAlignBits ;

public const uint kAlignMask = (kAlignTableSize - 1) ;

public const uint kStartPosModelIndex = 4 ;

public const uint kEndPosModelIndex = 14 ;

public const uint kNumPosModels = kEndPosModelIndex - kStartPosModelIndex ;

public const uint kNumFullDistances = 1 << ((int)kEndPosModelIndex / 2) ;

public const uint kNumLitPosStatesBitsEncodingMax = 4 ;

public const uint kNumLitContextBitsMax = 8 ;

public const int kNumPosStatesBitsMax = 4 ;

public const uint kNumPosStatesMax = (1 << kNumPosStatesBitsMax) ;

public const int kNumPosStatesBitsEncodingMax = 4 ;

public const uint kNumPosStatesEncodingMax = (1 << kNumPosStatesBitsEncodingMax) ;

public const int kNumLowLenBits = 3 ;

public const int kNumMidLenBits = 3 ;

public const int kNumHighLenBits = 8 ;

public const uint kNumLowLenSymbols = 1 << kNumLowLenBits ;

public const uint kNumMidLenSymbols = 1 << kNumMidLenBits ;

public const uint kNumLenSymbols = kNumLowLenSymbols + kNumMidLenSymbols +
(1 << kNumHighLenBits) ;

public const uint kMatchMaxLen = kMatchMinLen + kNumLenSymbols - 1 ;
```

#### GetLenToPosState

```csharp
public static uint GetLenToPosState(uint len) {
	len -= kMatchMinLen;
	if (len < kNumLenToPosStates)
		return len;
	return (uint)(kNumLenToPosStates - 1);
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/Lzma/LzmaBase.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
