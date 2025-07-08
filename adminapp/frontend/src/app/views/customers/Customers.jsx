import styled from "@mui/material/styles/styled";
import { SimpleCard } from "app/components";
import CustomersPanel from "./CustomersPanel";

import FormDialog from "./FormDialog";

// STYLED COMPONENTS
const CustomersRoot = styled("div")(({ theme }) => ({
  margin: "30px",
  "& .input": { display: "none" },
  "& .button": { margin: theme.spacing(1) },
  [theme.breakpoints.down("sm")]: { margin: "16px" },
  "& .breadcrumb": {
    marginBottom: "30px",
    [theme.breakpoints.down("sm")]: { marginBottom: "16px" }
  }
}));

export default function Customers() {
  return (
    <CustomersRoot>
      <FormDialog/>

      <SimpleCard title="客戶帳號列表">
        <CustomersPanel />
      </SimpleCard>      
    </CustomersRoot>
  );
}
