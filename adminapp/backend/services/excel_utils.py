# excel_utils.py
import asyncio
import pandas as pd
import sys

from backend.services.time_utils import format_datetime
from backend.repository.db_controller import db_controller


async def export_table_to_excel(table_name: str, output_filename: str):
    """
    從資料庫撈取整張資料表，並匯出成 Excel (.xlsx) 檔案。

    :param table_name: 要匯出的資料表名稱。
    :param output_filename: 匯出的 Excel 檔案路徑。
    """
    
    # 驗證 table_name 是否為空
    if not table_name:
        print("錯誤：必須提供 table_name。", file=sys.stderr)
        return
        
    # 確保副檔名是 .xlsx
    if not output_filename.endswith('.xlsx'):
        output_filename += '.xlsx'


    try:
        # 撈取所有資料
        # 使用 safe method，避免 SQL Injection
        try:
            data = await db_controller.get_all_by_tablename(table_name)
        except ValueError as e:
            print(f"錯誤：{e}")
            return

        if not data:
            print(f"資料表 '{table_name}' 中沒有資料，或資料表不存在。")
            return

        print(f"成功撈取 {len(data)} 筆資料。")
        
        # 處理時間戳資料
        processed_data = []
        for row in data:  # row 是一個 dict
            processed_row = {}
            for col_name, value in row.items():
                
                # 檢查：欄位是否以 _time 結尾，且值不是 None
                if col_name.endswith('_time') and value is not None:
                    
                    # Case 1: 值是一個 list (例如 access_time)
                    if isinstance(value, list) and value:
                        formatted_list = []
                        for ts in value:
                            try:
                                # 對 list 中的每個時間戳進行格式化
                                formatted_list.append(format_datetime(ts))
                            except (ValueError, TypeError, OSError):
                                # 處理 list 中可能的壞資料 (例如 None)
                                formatted_list.append(str(ts))
                        
                        # 在 Excel 中用換行符號分隔多個值
                        processed_row[col_name] = "\n".join(formatted_list)
                    
                    # Case 2: 值是單一數字 (例如 plan_time)
                    elif isinstance(value, (int, float)):
                        try:
                            processed_row[col_name] = format_datetime(value)
                        except (ValueError, TypeError, OSError):
                            # 處理無效的時間戳 (例如 0 或負數)
                            processed_row[col_name] = str(value) # 保留原值(轉字串)
                    
                    # Case 3: 值是其他類型 (例如空 list '[]' 或空 dict '{}')
                    else:
                        processed_row[col_name] = value
                
                # Case 4: 非 time 欄位，或值為 None
                else:
                    processed_row[col_name] = value
            
            processed_data.append(processed_row)

        print("時間戳格式化完成。")


        # 3. 將資料 (list[dict]) 轉換為 pandas DataFrame
        print("正在將資料轉換為 DataFrame...")
        df = pd.DataFrame(processed_data)

        # 4. 將 DataFrame 匯出為 Excel 檔案
        # index=False 表示不要將 pandas 的 index (0, 1, 2...) 寫入 Excel
        print(f"正在匯出資料至 '{output_filename}'...")
        df.to_excel(output_filename, index=False)

        print(f"\n成功！ 資料已從 '{table_name}' 匯出至 '{output_filename}'。")

    except Exception as e:
        print(f"發生錯誤：{e}", file=sys.stderr)
    finally:
        # 5. 確保資料庫連線池被關閉
        pass # engine cleanup is global or handled by caller if needed, specific close not strictly required for script unless hanging

# --- 程式執行入口 ---
if __name__ == "__main__":
    
    # --- 請修改這裡的設定 ---
    TABLE_TO_EXPORT = "users"  # <== 填入您要匯出的資料表名稱 (例如 "users", "accts")
    OUTPUT_FILE = "export_output.xlsx"   # <== 填入您要儲存的檔案名稱
    # --------------------------

    # 執行非同步主程式
    asyncio.run(export_table_to_excel(TABLE_TO_EXPORT, OUTPUT_FILE))