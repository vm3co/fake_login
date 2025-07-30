// import { useState } from "react";
// import { useNavigate } from "react-router-dom";
import Card from "@mui/material/Card";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import { styled } from "@mui/material/styles";
import { Formik } from "formik";
import * as Yup from "yup";


// STYLED COMPONENTS
const StyledRoot = styled("div")(() => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: "#1A2038",
  minHeight: "100vh !important",
  "& .card": {
    maxWidth: 800,
    margin: "1rem",
    borderRadius: 12
  },
  ".img-wrapper": {
    display: "flex",
    padding: "2rem",
    alignItems: "center",
    justifyContent: "center"
  }
}));

const ContentBox = styled("div")(({ theme }) => ({
  padding: 32,
  background: theme.palette.background.default
}));

const validationSchema = Yup.object().shape({
  oldPassword: Yup.string()
    .required("Old Password is required!"),
  newPassword: Yup.string()
    .notOneOf([Yup.ref("oldPassword"), null], "New Password must be different from Old Password")
    .required("New Password is required!"),
  confirmNewPassword: Yup.string()
    .oneOf([Yup.ref("newPassword"), null], "Passwords must match")
    .required("Confirm New Password is required!")
});


export default function ChangePassword() {
  const handleFormSubmit = (values) => {
    


    console.log(values.oldPassword);
    console.log(values.newPassword);
    console.log(values.confirmNewPassword);
  };

  const initialValues = {
    oldPassword: "",
    newPassword: "",
    confirmNewPassword: ""
  };

  return (
    <StyledRoot>
      <Card className="card">
        <div className="img-wrapper">
          <img width="300" src="/assets/images/illustrations/dreamer.svg" alt="Illustration" />
        </div>

        <ContentBox>
          <Formik
            onSubmit={handleFormSubmit}
            initialValues={initialValues}
            validationSchema={validationSchema}>
            {({
              values,
              errors,
              touched,
              isSubmitting,
              handleChange,
              handleBlur,
              handleSubmit
            }) => (
              <form onSubmit={handleSubmit}>
                <TextField
                  fullWidth
                  size="small"
                  name="oldPassword"
                  type="password"
                  label="舊密碼"
                  variant="outlined"
                  onBlur={handleBlur}
                  onChange={handleChange}
                  helperText={touched.oldPassword && errors.oldPassword}
                  error={Boolean(errors.oldPassword && touched.oldPassword)}
                  sx={{ mb: 2 }}
                />
                <TextField
                  fullWidth
                  size="small"
                  name="newPassword"
                  type="password"
                  label="新密碼"
                  variant="outlined"
                  onBlur={handleBlur}
                  value={values.newPassword}
                  onChange={handleChange}
                  helperText={touched.newPassword && errors.newPassword}
                  error={Boolean(errors.newPassword && touched.newPassword)}
                  sx={{ mb: 2 }}
                />
                <TextField
                  fullWidth
                  size="small"
                  name="confirmNewPassword"
                  type="password"
                  label="確認新密碼"
                  variant="outlined"
                  onBlur={handleBlur}
                  value={values.confirmNewPassword}
                  onChange={handleChange}
                  helperText={touched.confirmNewPassword && errors.confirmNewPassword}
                  error={Boolean(errors.confirmNewPassword && touched.confirmNewPassword)}
                  sx={{ mb: 2 }}
                />
                <Button
                  type="submit"
                  color="primary"
                  loading={isSubmitting}
                  variant="contained"
                  sx={{ my: 2 }}>
                  Change Password
                </Button>
              </form>
            )}
          </Formik>
        </ContentBox>
      </Card>
    </StyledRoot>
  );
}
