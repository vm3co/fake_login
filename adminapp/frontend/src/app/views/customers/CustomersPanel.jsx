import { useState } from 'react';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Box, Button, Divider } from '@mui/material';
import Accordion from '@mui/material/Accordion';
import AccordionActions from '@mui/material/AccordionActions';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Typography from '@mui/material/Typography';
import { styled } from '@mui/material';
import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";


const AccordionRoot = styled(Box)(({ theme }) => ({
  width: '100%',
  '& .heading': { fontSize: theme.typography.pxToRem(15) },
  '& .secondaryHeading': {
    color: theme.palette.text.secondary,
    fontSize: theme.typography.pxToRem(15)
  },
  '& .icon': {
    width: 20,
    height: 20,
    verticalAlign: 'bottom'
  },
  '& .details': { alignItems: 'center' },
  '& .column': { flexBasis: '33.33%' },
  '& .helper': {
    padding: theme.spacing(1, 2),
    borderLeft: `2px solid ${theme.palette.divider}`
  },
  '& .link': {
    textDecoration: 'none',
    color: theme.palette.primary.main,
    '&:hover': { textDecoration: 'underline' }
  }
}));

export default function CustomersPanel() {
  // 為每個客戶管理選中的 sendtasks
  const [customerSendtasks, setCustomerSendtasks] = useState({});

  // 處理 Autocomplete 選擇變化
  const handleSendtasksChange = (customerId, newValue) => {
    setCustomerSendtasks(prev => ({
      ...prev,
      [customerId]: newValue || []
    }));
  };


  return (
    <AccordionRoot>
      <Divider />

      <Box sx={{ marginBottom: 2 }}>
        {CustomersList.map((customer) => (
          <Box key={customer.id}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <Typography variant="body1">{customer.id}</Typography>
            </Box>
            <Accordion>
              <AccordionSummary
                expandIcon={<ExpandMoreIcon />}
                aria-controls="panel1c-content"
                id="panel1c-header"
              >
                <Box className="column">
                  <Typography className="heading">{customer.name}</Typography>
                </Box>

                {/* <Box className="column">
                  <Typography className="secondaryHeading">副標題</Typography>
                </Box> */}
              </AccordionSummary>

              <AccordionDetails className="details">

                <Box className="column helper">
                  <Autocomplete
                    multiple
                    filterSelectedOptions
                    id={`tags-outlined-${customer.id}`}
                    options={sendtasks}
                    getOptionLabel={(option) => option.title}
                    value={customerSendtasks[customer.id] || []}
                    onChange={(event, newValue) => handleSendtasksChange(customer.id, newValue)}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        fullWidth
                        variant="outlined"
                        placeholder="sendtasks"
                        label="choose sendtasks"
                      />
                    )}
                  />
                </Box>
              </AccordionDetails>

              <Divider />

              <AccordionActions>
                <Button size="small">Cancel</Button>
                <Button 
                  size="small" 
                  color="primary"
                  onClick={() => {
                    // 這裡可以處理保存邏輯
                    console.log(`客戶 ${customer.name} 的 sendtasks:`, customerSendtasks[customer.id]);
                  }}
                >
                    Save
                </Button>
              </AccordionActions>
            </Accordion>
          </Box>
        ))}
      </Box>

    </AccordionRoot>
  );
}

const CustomersList = [
  {
    id: 1,
    name: 'John Doe',
    email: 'john.doe@example.com',
  },
  {
    id: 2,
    name: 'Jane Smith',
    email: 'jane.smith@example.com',
  },
  {
    id: 3,
    name: 'Alice Johnson',
    email: 'alice.johnson@example.com',
  }
]

const sendtasks = [
  { title: "新析生物-114S前測_0702", year: 1994 },
  { title: "消防署114S2-正式演練", year: 1972 },
  { title: "114Q3-JCIC-正式", year: 1974 },
  { title: "中龍鋼鐵114S2-正式演練", year: 2008 },
  { title: "114S1-海基會-正式", year: 1957 },
  { title: "消防署114S1前測_0626", year: 1993 },
  { title: "大綜兆利科技114S1複測_前測", year: 1994 },
  { title: "2025S1-台肥-正式", year: 2003 },
];
