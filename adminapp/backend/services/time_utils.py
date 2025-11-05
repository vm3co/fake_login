import datetime

def format_datetime(
        timestamp: float, 
        format_str: str = "%Y-%m-%d %H:%M:%S"
    ) -> str:
    """
    將 Unix 時間戳轉換為指定格式的日期時間字串。

    :param timestamp: Unix 時間戳 (float 或 int)。
    :param format_str: (可選) 輸出的字串格式。
    :return: 格式化後的日期時間字串。
    """
    if not timestamp or not isinstance(timestamp, (int, float)) or timestamp == 0:
        return ""
    try:
        dt_object = datetime.datetime.fromtimestamp(timestamp)
        return dt_object.strftime(format_str)
    except (ValueError, TypeError, OSError):
        return ""
    
def get_current_time(
        format_str: str = "%Y-%m-%d %H:%M:%S"
    ) -> str:
    """
    取得當下的時間。
    :param format_str: (可選) 輸出的字串格式。
    :return: 格式化後的日期時間字串。
    """
    current_time = datetime.datetime.now()
    return current_time.strftime(format_str)

def convert_str_to_timestamp(
        datetime_str: str, 
        format_str: str = "%Y-%m-%d %H:%M:%S",
        as_integer: bool = True
    ) -> int | float:
    """
    將格式化的日期時間字串轉換回 Unix 時間戳。

    :param datetime_str: 日期時間字串 (例如 "2023-10-27 10:00:00")。
    :param format_str: (可選) 傳入字串所對應的格式。
    :param as_integer: (可選) 是否將輸出的時間戳轉為整數（去除毫秒）。
                    預設為 True (輸出整數)。
    :return: Unix 時間戳 (int 或 float)。
    """
    try:
        # 使用 strptime (string parse time) 將字串解析為 datetime 物件
        dt_object = datetime.datetime.strptime(datetime_str, format_str)        
        # 使用 .timestamp() 將 datetime 物件轉為時間戳 (這會是 float)
        ts = dt_object.timestamp()        
        # 根據 as_integer 參數決定回傳類型
        return int(ts) if as_integer else ts
        
    except ValueError as e:
        print(f"錯誤：時間字串 '{datetime_str}' 與格式 '{format_str}' 不匹配。{e}")
        return 0

def get_current_timestamp(
        as_integer: bool = True
    ) -> int | float:
    """
    取得當下的 Unix 時間戳。

    :param as_integer: (可選) 是否回傳整數（去除毫秒）。預設為 True。
    :return: Unix 時間戳 (int 或 float)。
    """
    ts = datetime.datetime.now().timestamp()
    return int(ts) if as_integer else ts

# --- 程式執行範例 ---
if __name__ == "__main__":

    print("------ 取得當下時間戳 (get_current_timestamp) ------")
    # 1. 取得當下時間戳 (預設整數)
    ts_int = get_current_timestamp()
    print(f"當下時間戳 (整數): {ts_int}")

    # 2. 取得當下時間戳 (float)
    ts_float = get_current_timestamp(as_integer=False)
    print(f"當下時間戳 (Float): {ts_float}")


    print("\n------ 將時間戳轉為字串 (format_datetime) ------")
    # 3. 用剛才的 float 時間戳來格式化
    time_str = format_datetime(ts_float)
    print(f"時間戳 {ts_float} 轉為字串: {time_str}")


    print("\n------ 將字串轉回時間戳 (convert_str_to_timestamp) ------")
    # 4. 將時間字串轉回時間戳 (預設整數)
    my_str = "2023-03-15 16:00:00"
    ts_from_str_int = convert_str_to_timestamp(my_str)
    print(f"字串 '{my_str}' 轉回時間戳 (整數): {ts_from_str_int}")

    # 5. 將時間字串轉回時間戳 (指定 float)
    #    (注意：因為來源字串沒有毫秒，所以 .0 結尾)
    ts_from_str_float = convert_str_to_timestamp(my_str, as_integer=False)
    print(f"字串 '{my_str}' 轉回時間戳 (Float): {ts_from_str_float}")