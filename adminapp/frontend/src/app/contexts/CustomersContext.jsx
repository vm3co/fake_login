import { createContext } from "react";
import useCustomers from "app/hooks/useCustomers";

const CustomersContext = createContext(null);

export const CustomersProvider = ({ children }) => {
  const customerData = useCustomers();

  return (
    <CustomersContext.Provider value={customerData}>
      {children}
    </CustomersContext.Provider>
  );
};

export default CustomersContext;