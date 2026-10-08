# ArcFormats / ArcCommon：归档读取与解码

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

### GameRes.Formats.MMX

#### PAddB

```csharp
public static ulong PAddB (ulong x, ulong y) {
    ulong r = 0;
    for (ulong mask = 0xFF; mask != 0; mask <<= 8)
    {
        r |= ((x & mask) + (y & mask)) & mask;
    }
    return r;
}
```

#### PAddB

```csharp
public static uint PAddB (uint x, uint y) {
    uint r13 = (x & 0xFF00FF00u) + (y & 0xFF00FF00u);
    uint r02 = (x & 0x00FF00FFu) + (y & 0x00FF00FFu);
    return (r13 & 0xFF00FF00u) | (r02 & 0x00FF00FFu);
}
```

#### PAddW

```csharp
public static ulong PAddW (ulong x, ulong y) {
    ulong mask = 0xffff;
    ulong r = ((x & mask) + (y & mask)) & mask;
    mask <<= 16;
    r |= ((x & mask) + (y & mask)) & mask;
    mask <<= 16;
    r |= ((x & mask) + (y & mask)) & mask;
    mask <<= 16;
    r |= ((x & mask) + (y & mask)) & mask;
    return r;
}
```

#### PAddD

```csharp
public static ulong PAddD (ulong x, ulong y) {
    ulong mask = 0xffffffff;
    ulong r = ((x & mask) + (y & mask)) & mask;
    mask <<= 32;
    return r | ((x & mask) + (y & mask)) & mask;
}
```

#### PSubB

```csharp
public static ulong PSubB (ulong x, ulong y) {
    ulong r = 0;
    for (ulong mask = 0xFF; mask != 0; mask <<= 8)
    {
        r |= ((x & mask) - (y & mask)) & mask;
    }
    return r;
}
```

#### PSubW

```csharp
public static ulong PSubW (ulong x, ulong y) {
    ulong mask = 0xffff;
    ulong r = ((x & mask) - (y & mask)) & mask;
    mask <<= 16;
    r |= ((x & mask) - (y & mask)) & mask;
    mask <<= 16;
    r |= ((x & mask) - (y & mask)) & mask;
    mask <<= 16;
    r |= ((x & mask) - (y & mask)) & mask;
    return r;
}
```

#### PSubD

```csharp
public static ulong PSubD (ulong x, ulong y) {
    ulong mask = 0xffffffff;
    ulong r = ((x & mask) - (y & mask)) & mask;
    mask <<= 32;
    return r | ((x & mask) - (y & mask)) & mask;
}
```

#### PSllD

```csharp
public static ulong PSllD (ulong x, int count) {
    count &= 0x1F;
    ulong mask = 0xFFFFFFFFu << count;
    mask |= mask << 32;
    return (x << count) & mask;
}
```

#### PSrlD

```csharp
public static ulong PSrlD (ulong x, int count) {
    count &= 0x1F;
    ulong mask = 0xFFFFFFFFu >> count;
    mask |= mask << 32;
    return (x >> count) & mask;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/ArcCommon.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
