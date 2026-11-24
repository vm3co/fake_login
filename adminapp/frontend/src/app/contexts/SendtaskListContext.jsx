import { createContext } from "react";
import useSendtaskList from "app/hooks/useSendtaskList";

/**
 * SendtaskListContext 用於提供任務列表的上下文。
 * 預設值包含 loading 屬性，避免未包裹時出現解構錯誤。
 */
export const SendtaskListContext = createContext({ loading: true });

export const SendtaskListProvider = ({ children }) => {
  const sendtaskList = useSendtaskList();
  return (
    <SendtaskListContext.Provider value={sendtaskList}>
      {children}
    </SendtaskListContext.Provider>
  );
};