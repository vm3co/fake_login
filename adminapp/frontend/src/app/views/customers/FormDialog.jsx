import { useState, forwardRef } from "react";
import AppBar from "@mui/material/AppBar";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import TextField from "@mui/material/TextField";
import DialogTitle from "@mui/material/DialogTitle";
// import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import Fab from "@mui/material/Fab";
import Icon from "@mui/material/Icon";
import Box from "@mui/material/Box";
import Slide from "@mui/material/Slide";
import Toolbar from "@mui/material/Toolbar";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import Autocomplete from "@mui/material/Autocomplete";


const Transition = forwardRef(function Transition(props, ref) {
  return <Slide direction="up" ref={ref} {...props} />;
});

export default function FormDialog() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({
    customername: "",
    customerfullname: "",
    password: "",
    confirmPassword: ""
  });


  const handleClickOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  const handleSubmit = (event) => {
    console.log("submitted");
    console.log(event);
  };

  const handleChange = (event) => {
    event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  const { customername, customerfullname, password, confirmPassword } =
    state;


  return (
    <div>
      <Box display="flex" justifyContent="flex-end" alignItems="center" gap={1}>
        <Fab size="medium" color="secondary" aria-label="Add" className="button" onClick={handleClickOpen}>
          <Icon>add user</Icon>
        </Fab>
        <h3>新增帳號</h3>
      </Box>

      <Dialog open={open} onClose={handleClose} TransitionComponent={Transition}>
        <AppBar sx={{ position: "relative" }}>
          <Toolbar>
            <IconButton edge="start" color="inherit" onClick={handleClose} aria-label="Close">
              <CloseIcon />
            </IconButton>
          </Toolbar>
        </AppBar>

        <form onSubmit={handleSubmit}>

          <DialogTitle id="form-dialog-title">新增帳號</DialogTitle>

          <DialogContent>
            <DialogContentText>
              提供給客戶使用的帳號
            </DialogContentText>

            <TextField
              sx={{ mb: 1 }}
              fullWidth
              type="text"
              name="customername"
              value={customername}
              onChange={handleChange}
              label="Customer Name(僅可輸入英文及數字)"
            />
            <TextField
              sx={{ mb: 1 }}
              fullWidth
              name="password"
              type="password"
              label="Password"
              value={password}
              onChange={handleChange}
            />
            <TextField
              sx={{ mb: 1 }}
              fullWidth
              type="password"
              name="confirmPassword"
              onChange={handleChange}
              label="Confirm Password"
              value={confirmPassword}
            />
            <TextField
              sx={{ mb: 1 }}
              fullWidth
              type="text"
              name="customerfullname"
              value={customerfullname}
              onChange={handleChange}
              label="Customer Full Name"
            />
            <Autocomplete
              multiple
              filterSelectedOptions
              id="tags-outlined"
              options={sendtasks}
              getOptionLabel={(option) => option.title}
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
          </DialogContent>

          <Box display="flex" justifyContent="center" alignItems="center" gap={1} sx={{ mb: 1 }}>
            <Button variant="outlined" onClick={handleClose} color="primary">
              新增
            </Button>
          </Box>
        </form>
        <Box display="flex" justifyContent="center" alignItems="center" gap={1} sx={{ mb: 1 }}>
          <Button variant="outlined" color="secondary" onClick={handleClose}>
            取消
          </Button>
        </Box>
      </Dialog>
    </div>
  );
}


//暫時使用，之後要將sendtasks帶入
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
