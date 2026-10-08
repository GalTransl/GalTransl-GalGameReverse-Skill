# RenPy / ArcRPA：归档读取与解码

算法资料，未执行验证；不改变随包支持声明。API、边界和外部参数见 [读取约定](../../reading.md)。

## 格式入口

| 标识/API | 扩展名 | 文件头候选（u32 小端字节） | 来源写入声明 |
|---|---|---|---|
| `RPA` / `GameRes.Formats.RenPy.RpaOpener` | `rpa` | `5250412d` | `True` |

## 字段与结构读取

以下保留源码的偏移表达式。`entry.Offset` 为最终成员跨度；`base_offset + offset` 等表达式中的基址以算法摘录为准。表中重复读取可属于不同版本或分支，不能拼成一个假定的统一头部。

| 算法位置 | 读取表达式 |
|---|---|
| `RpaOpener.TryOpen` | `if (0x20302e33 != file.View.ReadUInt32 (4))` |
| `RpaOpener.TryOpen` | `string index_offset_str = file.View.ReadString (8, 16, Encoding.ASCII);` |
| `RpaOpener.TryOpen` | `string key_str = file.View.ReadString (0x19, 8, Encoding.ASCII);` |
| `RpaOpener.TryOpen` | `entry.Offset       = (long)(Convert.ToInt64 (tuple[0]) ^ key);` |
| `RpaOpener.TryOpen` | `entry.UnpackedSize = (uint)(Convert.ToInt64 (tuple[1]) ^ key);` |
| `Pickle.Load` | `int sym = m_stream.ReadByte();` |
| `Pickle.LoadProto` | `int i = m_stream.ReadByte();` |
| `Pickle.LoadBinPut` | `int key = m_stream.ReadByte();` |
| `Pickle.LoadShortBinstring` | `int length = m_stream.ReadByte();` |
| `Pickle.ReadInt` | `int b = m_stream.ReadByte();` |
| `Pickle.LoadLong` | `int count = m_stream.ReadByte();` |
| `Pickle.DecodeLong` | `return bytes.ToInt64 (0);` |

## 读取、解密与解压步骤

按所属类和入口选择分支，固定常量只用于引用它们的方言。外部方案库需要显式参数；摘录省略 writer、GUI 和资源注册。

### GameRes.Formats.RenPy.RpaEntry

继承/接口：`PackedEntry`。

#### 状态与常量

```csharp
public byte[] Header = null ;
```

### GameRes.Formats.RenPy.RpaOpener

继承/接口：`ArchiveFormat`。

#### TryOpen

```csharp
public override ArcFile TryOpen (ArcView file) {
    if (0x20302e33 != file.View.ReadUInt32 (4))
        return null;
    string index_offset_str = file.View.ReadString (8, 16, Encoding.ASCII);
    long index_offset;
    if (!long.TryParse (index_offset_str, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out index_offset))
        return null;
    if (index_offset >= file.MaxOffset)
        return null;
    uint key;
    string key_str = file.View.ReadString (0x19, 8, Encoding.ASCII);
    if (!uint.TryParse (key_str, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out key))
        return null;

    IDictionary dict = null;
    using (var index = new ZLibStream (file.CreateStream (index_offset), CompressionMode.Decompress))
    {
        var pickle = new Pickle (index);
        dict = pickle.Load() as IDictionary;
    }
    if (null == dict)
        return null;
    var dir = new List<Entry> (dict.Count);
    foreach (DictionaryEntry item in dict)
    {
        var name_raw = item.Key as byte[];
        var values = item.Value as IList;
        if (null == name_raw || null == values || values.Count < 1)
        {
            Trace.WriteLine ("invalid index entry", "RpaOpener.TryOpen");
            return null;
        }
        string name = Encoding.UTF8.GetString (name_raw);
        if (string.IsNullOrEmpty (name))
            return null;
        var tuple = values[0] as IList;
        if (null == tuple || tuple.Count < 2)
        {
            Trace.WriteLine ("invalid index tuple", "RpaOpener.TryOpen");
            return null;
        }
        var entry = FormatCatalog.Instance.Create<RpaEntry> (name);
        entry.Offset       = (long)(Convert.ToInt64 (tuple[0]) ^ key);
        entry.UnpackedSize = (uint)(Convert.ToInt64 (tuple[1]) ^ key);
        entry.Size         = entry.UnpackedSize;
        if (tuple.Count > 2)
        {
            entry.Header = tuple[2] as byte[];
            if (null != entry.Header && entry.Header.Length > 0)
            {
                entry.Size -= (uint)entry.Header.Length;
                entry.IsPacked = true;
            }
        }
        dir.Add (entry);
    }
    if (dir.Count > 0)
        Trace.TraceInformation ("[{0}] [{1:X8}] [{2}]", dir[0].Name, dir[0].Offset, dir[0].Size);
    return new ArcFile (file, this, dir);
}
```

#### OpenEntry

```csharp
public override Stream OpenEntry (ArcFile arc, Entry entry) {
    Stream input;
    if (0 != entry.Size)
        input = arc.File.CreateStream (entry.Offset, entry.Size);
    else
        input = Stream.Null;
    var rpa_entry = entry as RpaEntry;
    if (null == rpa_entry || null == rpa_entry.Header || 0 == rpa_entry.Header.Length)
        return input;
    return new PrefixStream (rpa_entry.Header, input);
}
```

### GameRes.Formats.RenPy.Pickle

#### 状态与常量

```csharp
Stream          m_stream ;

ArrayList       m_stack = new ArrayList() ;

Stack<int>      m_marks = new Stack<int>() ;

const int HIGHEST_PROTOCOL  = 2 ;

const int BATCHSIZE         = 1000 ;

const byte PROTO            = 0x80 ;

const byte TUPLE2           = 0x86 ;

const byte TUPLE3           = 0x87 ;

const byte LONG1            = 0x8A ;

const byte LONG4            = 0x8B ;

const byte MARK             = (byte)'(' ;

const byte STOP             = (byte)'.' ;

const byte INT              = (byte)'I' ;

const byte BININT           = (byte)'J' ;

const byte BININT1          = (byte)'K' ;

const byte BININT2          = (byte)'M' ;

const byte BINSTRING        = (byte)'T' ;

const byte SHORT_BINSTRING  = (byte)'U' ;

const byte BINUNICODE       = (byte)'X' ;

const byte EMPTY_LIST       = (byte)']' ;

const byte APPEND           = (byte)'a' ;

const byte APPENDS          = (byte)'e' ;

const byte BINPUT           = (byte)'q' ;

const byte LONG_BINPUT      = (byte)'r' ;

const byte SETITEM          = (byte)'s' ;

const byte TUPLE            = (byte)'t' ;

const byte SETITEMS         = (byte)'u' ;

const byte EMPTY_DICT       = (byte)'}' ;
```

#### Pickle

```csharp
public Pickle (Stream stream) {
    m_stream = stream;
}
```

#### Dump

```csharp
public bool Dump (object obj) {
    m_stream.WriteByte (PROTO);
    m_stream.WriteByte ((byte)HIGHEST_PROTOCOL);
    if (!Save (obj))
        return false;
    m_stream.WriteByte (STOP);
    return true;
}
```

#### Save

```csharp
bool Save (object obj) {
    if (null == obj)
    {
        Trace.WriteLine ("Null reference not serialized", "Pickle.Save");
        return false;
    }
    switch (Type.GetTypeCode (obj.GetType()))
    {
    case TypeCode.Byte:     return SaveInt ((uint)(byte)obj);
    case TypeCode.SByte:    return SaveInt ((uint)(sbyte)obj);
    case TypeCode.UInt16:   return SaveInt ((uint)(ushort)obj);
    case TypeCode.Int16:    return SaveInt ((uint)(short)obj);
    case TypeCode.Int32:    return SaveInt ((uint)(int)obj);
    case TypeCode.UInt32:   return SaveInt ((uint)obj);
    case TypeCode.Int64:    return SaveLong ((long)obj);
    case TypeCode.UInt64:   return SaveLong ((long)(ulong)obj);
    case TypeCode.Object:   break;
    default:
        Trace.WriteLine (obj, "Object could not be serialized");
        return false;
    }
    if (obj is RpaEntry)
        return SaveEntry (obj as RpaEntry);
    if (obj is PyString)
        return SaveString (obj as PyString);
    if (obj is byte[])
        return SaveString (obj as byte[]);
    if (obj is IDictionary)
        return SaveDict (obj as IDictionary);
    if (obj is IList)
        return SaveList (obj as IList);

    Trace.WriteLine (obj, "Object could not be serialized");
    return false;
}
```

#### SaveString

```csharp
bool SaveString (byte[] str) {
    int size = str.Length;
    if (size < 256)
    {
        m_stream.WriteByte (SHORT_BINSTRING);
        m_stream.WriteByte ((byte)size);
    }
    else
    {
        m_stream.WriteByte (BINSTRING);
        PutInt (size);
    }
    m_stream.Write (str, 0, size);
    return true;
}
```

#### SaveString

```csharp
bool SaveString (PyString str) {
    if (str.IsAscii)
        return SaveString (str.Bytes);
    m_stream.WriteByte (BINUNICODE);
    PutInt (str.Length);
    m_stream.Write (str.Bytes, 0, str.Length);
    return true;
}
```

#### SaveEntry

```csharp
bool SaveEntry (RpaEntry entry) {
    byte opcode = null == entry.Header ? TUPLE2 : TUPLE3;
    SaveLong (entry.Offset);
    SaveInt (entry.UnpackedSize);
    if (null != entry.Header)
        SaveString (entry.Header);
    m_stream.WriteByte (opcode);
    return true;
}
```

#### SaveList

```csharp
bool SaveList (IList list) {
    m_stream.WriteByte (EMPTY_LIST);
    if (0 == list.Count)
        return true;
    return BatchList (list.GetEnumerator());
}
```

#### BatchList

```csharp
bool BatchList (IEnumerator iterator) {
    int n = 0;
    do
    {
        if (!iterator.MoveNext())
            break;
        var first_item = iterator.Current;
        if (!iterator.MoveNext())
        {
            if (!Save (first_item))
                return false;
            m_stream.WriteByte (APPEND);
            break;
        }
        m_stream.WriteByte (MARK);
        if (!Save (first_item))
            return false;
        n = 1;
        do
        {
            if (!Save (iterator.Current))
                return false;
            if (++n == BATCHSIZE)
                break;
        }
        while (iterator.MoveNext());
        m_stream.WriteByte (APPENDS);
    }
    while (n == BATCHSIZE);
    return true;
}
```

#### SaveInt

```csharp
bool SaveInt (uint i) {
    byte[] buf = new byte[5];
    buf[1] = (byte)( i        & 0xff);
    buf[2] = (byte)((i >> 8)  & 0xff);
    buf[3] = (byte)((i >> 16) & 0xff);
    buf[4] = (byte)((i >> 24) & 0xff);
    int length;
    if (0 == buf[4] && 0 == buf[3])
    {
        if (0 == buf[2])
        {
            buf[0] = BININT1;
            length = 2;
        }
        else
        {
            buf[0] = BININT2;
            length = 3;
        }
    }
    else
    {
        buf[0] = BININT;
        length = 5;
    }
    m_stream.Write (buf, 0, length);
    return true;
}
```

#### SaveLong

```csharp
bool SaveLong (long l) {
    if (0 == ((l >> 32) & 0xffffffff))
        return SaveInt ((uint)l);
    m_stream.WriteByte (INT);
    string num = l.ToString (CultureInfo.InvariantCulture);
    var num_data = Encoding.ASCII.GetBytes (num);
    m_stream.Write (num_data, 0, num_data.Length);
    m_stream.WriteByte (0x0a);
    return true;
}
```

#### SaveDict

```csharp
bool SaveDict (IDictionary dict) {
    m_stream.WriteByte (EMPTY_DICT);
    if (0 == dict.Count)
        return true;
    return BatchDict (dict);
}
```

#### BatchDict

```csharp
bool BatchDict (IDictionary dict) {
    int dict_size = dict.Count;
    var iterator = dict.GetEnumerator();
    if (1 == dict_size)
    {
        if (!iterator.MoveNext())
            return false;
        if (!Save (iterator.Key))
            return false;
        if (!Save (iterator.Value))
            return false;
        m_stream.WriteByte (SETITEM);
        return true;
    }
    int i;
    do
    {
        i = 0;
        m_stream.WriteByte (MARK);
        while (iterator.MoveNext())
        {
            if (!Save (iterator.Key))
                return false;
            if (!Save (iterator.Value))
                return false;
            if (++i == BATCHSIZE)
                break;
        }
        m_stream.WriteByte (SETITEMS);
    }
    while (i == BATCHSIZE);
    return true;
}
```

#### PutInt

```csharp
bool PutInt (int i) {
    m_stream.WriteByte ((byte)(i & 0xff));
    m_stream.WriteByte ((byte)((i >> 8) & 0xff));
    m_stream.WriteByte ((byte)((i >> 16) & 0xff));
    m_stream.WriteByte ((byte)((i >> 24) & 0xff));
    return true;
}
```

#### Load

```csharp
public object Load () {
    for (;;)
    {
        int sym = m_stream.ReadByte();
        switch (sym)
        {
        case PROTO:
            if (!LoadProto())
                break;
            continue;

        case EMPTY_DICT:
            if (!LoadEmptyDict())
                break;
            continue;

        case BINPUT:
            if (!LoadBinPut())
                break;
            continue;

        case LONG_BINPUT:
            if (!LoadLongBinPut())
                break;
            continue;

        case MARK:
            if (!LoadMark())
                break;
            continue;

        case SHORT_BINSTRING:
            if (!LoadShortBinstring())
                break;
            continue;

        case BINSTRING:
        case BINUNICODE:
            if (!LoadBinUnicode())
                break;
            continue;

        case EMPTY_LIST:
            if (!LoadEmptyList())
                break;
            continue;

        case BININT:
            if (!LoadBinInt (4))
                break;
            continue;

        case BININT1:
            if (!LoadBinInt (1))
                break;
            continue;

        case BININT2:
            if (!LoadBinInt (2))
                break;
            continue;

        case INT:
            if (!LoadInt())
                break;
            continue;

        case TUPLE2:
            if (!LoadCountedTuple (2))
                break;
            continue;

        case TUPLE3:
            if (!LoadCountedTuple (3))
                break;
            continue;

        case LONG1:
            if (!LoadLong())
                break;
            continue;

        case LONG4:
            if (!LoadLong4())
                break;
            continue;

        case APPEND:
            if (!LoadAppend())
                break;
            continue;

        case SETITEM:
            if (!LoadSetItem())
                break;
            continue;

        case SETITEMS:
            if (!LoadSetItems())
                break;
            continue;

        case STOP:
            break;

        case -1:
        case 0:
            Trace.WriteLine ("Unexpected end of file", "Pickle.Load");
            return null;

        default:
            Trace.TraceError ("Unknown Pickle serialization opcode 0x{0:X2}", sym);
            return null;
        }
        break;
    }
    if (0 == m_stack.Count)
    {
        Trace.WriteLine ("Invalid pickle data", "Pickle.Load");
        return null;
    }
    return m_stack.Pop();
}
```

#### LoadProto

```csharp
bool LoadProto () {
    int i = m_stream.ReadByte();
    if (-1 == i)
        return false;
    if (i > HIGHEST_PROTOCOL)
        return false;
    return true;
}
```

#### LoadEmptyDict

```csharp
bool LoadEmptyDict () {
    m_stack.Push (new Hashtable());
    return true;
}
```

#### LoadBinPut

```csharp
bool LoadBinPut () {
    int key = m_stream.ReadByte();
    if (-1 == key || 0 == m_stack.Count)
        return false;
    return true;
}
```

#### LoadLongBinPut

```csharp
bool LoadLongBinPut () {
    int key;
    if (!ReadInt (4, out key) || 0 == m_stack.Count || key < 0)
        return false;
    return true;
}
```

#### LoadMark

```csharp
bool LoadMark () {
    m_marks.Push (m_stack.Count);
    return true;
}
```

#### GetMarker

```csharp
int GetMarker () {
    if (0 == m_marks.Count)
    {
        Trace.TraceError ("MARK list is empty");
        return -1;
    }
    return m_marks.Pop();
}
```

#### LoadShortBinstring

```csharp
bool LoadShortBinstring () {
    int length = m_stream.ReadByte();
    if (-1 == length)
        return false;
    return LoadBinString (length);
}
```

#### LoadBinUnicode

```csharp
bool LoadBinUnicode () {
    int length;
    if (!ReadInt (4, out length))
        return false;
    return LoadBinString (length);
}
```

#### LoadBinString

```csharp
bool LoadBinString (int length) {
    var bytes = new byte[length];
    if (length != m_stream.Read (bytes, 0, length))
        return false;
    m_stack.Push (bytes);
    return true;
}
```

#### LoadEmptyList

```csharp
bool LoadEmptyList () {
    m_stack.Push (new ArrayList());
    return true;
}
```

#### ReadInt

```csharp
bool ReadInt (int size, out int value) {
    value = 0;
    for (int i = 0; i < size; ++i)
    {
        int b = m_stream.ReadByte();
        if (-1 == b)
            return false;
        value |= b << (i * 8);
    }
    return true;
}
```

#### LoadBinInt

```csharp
bool LoadBinInt (int size) {
    int x = 0;
    if (!ReadInt (size, out x))
        return false;
    m_stack.Push (x);
    return true;
}
```

#### LoadInt

```csharp
bool LoadInt () {
    var num = m_stream.ReadStringUntil (0x0a, Encoding.ASCII);
    long n;
    if (!long.TryParse (num, NumberStyles.Integer, CultureInfo.InvariantCulture, out n))
        return false;
    m_stack.Push (n);
    return true;
}
```

#### LoadLong

```csharp
bool LoadLong () {
    int count = m_stream.ReadByte();
    if (-1 == count)
        return false;
    m_stack.Push (DecodeLong (count));
    return true;
}
```

#### LoadLong4

```csharp
bool LoadLong4 () {
    int count = 0;
    if (!ReadInt (4, out count) || count < 0)
        return false;
    m_stack.Push (DecodeLong (count));
    return true;
}
```

#### DecodeLong

```csharp
object DecodeLong (int count) {
    if (count <= 0)
        return 0L;
    else if (count > 8)
    {
        var bytes = new byte[count];
        m_stream.Read (bytes, 0, count);
        return new BigInteger (bytes);
    }
    else
    {
        var bytes = new byte[8];
        m_stream.Read (bytes, 0, count);
        if (0 != (bytes[count-1] & 0x80))
        {
            for (int i = count; i < bytes.Length; ++i)
                bytes[i] = 0xFF;
        }
        return bytes.ToInt64 (0);
    }
}
```

#### LoadCountedTuple

```csharp
bool LoadCountedTuple (int count) {
    if (m_stack.Count < count)
        return false;
    var tuple = new ArrayList (count);
    while (--count >= 0)
    {
        var item = m_stack.Pop();
        tuple.Add (item);
    }
    tuple.Reverse();
    m_stack.Push (tuple);
    return true;
}
```

#### LoadAppend

```csharp
bool LoadAppend () {
    int x = m_stack.Count - 1;
    if (x <= 0)
    {
        Trace.WriteLine ("Stack underflow", "LoadAppend");
        return false;
    }
    var list = m_stack[x-1] as ArrayList;
    if (null == list)
    {
        Trace.WriteLine ("Object is not a list", "LoadAppend");
        return false;
    }
    var slice = PdataPopList (x);
    if (null == slice)
        return false;
    list.AddRange (slice);
    return true;
}
```

#### PdataPopList

```csharp
ArrayList PdataPopList (int start) {
    int count = m_stack.Count - start;
    var list = new ArrayList (count);
    for (int i = start; i < m_stack.Count; ++i)
        list.Add (m_stack[i]);
    m_stack.RemoveRange (start, count);
    return list;
}
```

#### LoadSetItem

```csharp
bool LoadSetItem () {
    return DoSetItems (m_stack.Count-2);
}
```

#### LoadSetItems

```csharp
bool LoadSetItems () {
    return DoSetItems (GetMarker());
}
```

#### DoSetItems

```csharp
bool DoSetItems (int mark) {
    if (!(m_stack.Count >= mark && mark > 0))
    {
        Trace.WriteLine ("Stack underflow", "LoadSetItems");
        return false;
    }
    var dict = m_stack[mark-1] as Hashtable;
    if (null == dict)
    {
        Trace.WriteLine ("Marked object is not a dictionary", "LoadSetItems");
        return false;
    }
    for (int i = mark+1; i < m_stack.Count; i += 2)
    {
        var key   = m_stack[i-1];
        var value = m_stack[i];
        dict[key] = value;
    }
    return PdataClear (mark);
}
```

#### PdataClear

```csharp
bool PdataClear (int clearto) {
    if (clearto < 0)
        return false;
    if (clearto < m_stack.Count)
        m_stack.RemoveRange (clearto, m_stack.Count-clearto);
    return true;
}
```

### GameRes.Formats.RenPy.PyString

继承/接口：`IEquatable<PyString>`。

#### 状态与常量

```csharp
int         m_hash ;

byte[]      m_bytes ;

Lazy<bool>  m_is_ascii ;

public bool IsAscii { get { return m_is_ascii.Value; } }

public byte[] Bytes { get { return m_bytes; } }

public int   Length { get { return m_bytes.Length; } }
```

#### PyString

```csharp
public PyString (string s) {
    m_hash = s.GetHashCode();
    m_bytes = Encoding.UTF8.GetBytes (s);
    m_is_ascii = new Lazy<bool> (() => -1 == Array.FindIndex (m_bytes, x => x > 0x7f));
}
```

#### Equals

```csharp
public bool Equals (PyString other) {
    if (null == other)
        return false;
    if (this.m_hash != other.m_hash)
        return false;
    if (this.Length != other.Length)
        return false;
    for (var i = 0; i < m_bytes.Length; ++i)
        if (m_bytes[i] != other.m_bytes[i])
            return false;
    return true;
}
```

#### Equals

```csharp
public override bool Equals (object other) {
    return this.Equals (other as PyString);
}
```

#### GetHashCode

```csharp
public override int GetHashCode () {
    return m_hash;
}
```

## 配套算法与外部条件

本源文件没有解析到其他专用算法依赖；标准压缩、框架 API 和显式游戏参数的约定仍见读取约定。

## 出处与许可

来源文件标识 `ArcFormats/RenPy/ArcRPA.cs`；版本、UTF-8 解码内容哈希与版权/许可通知见 [出处清单](../../../../provenance/garbro-archive-excerpts.json)和 [原通知](../../../../provenance/garbro-archive-notices.md)。路径是出处，不是使用时需要访问的外部文件。
