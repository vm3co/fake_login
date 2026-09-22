import Box from "@mui/material/Box";
import styled from "@mui/material/styles/styled";

// import { Span } from "./Typography";
// import { MatxLogo } from "app/components";
import useSettings from "app/hooks/useSettings";

import LogoAcsi from "/assets/images/logo-acsi.png";


// STYLED COMPONENTS
const BrandRoot = styled("div")(({ mode }) => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "20px 18px 20px 29px",
  transition: "all 0.3s ease",
  ...(mode === "compact" && {
    padding: "20px 10px",
    justifyContent: "center"
  })
}));

// const StyledSpan = styled(Span)(({ mode }) => ({
//   fontSize: 18,
//   marginLeft: ".5rem",
//   display: mode === "compact" ? "none" : "block"
// }));

//logo
const CustomLogo = styled("img")(({ mode }) => ({
  width: "96px",
  height: "64px",
  objectFit: "contain",
  transition: "all 0.3s ease",
  ...(mode === "compact" && {
    width: "50px",
    height: "40px"
  })
}));

export default function Brand({ children }) {
  const { settings } = useSettings();
  const leftSidebar = settings.layout1Settings.leftSidebar;
  const { mode } = leftSidebar;

  return (
    <BrandRoot mode={mode} className="brand-root">
      <Box display="flex" alignItems="center">
        <CustomLogo src={LogoAcsi} alt="Company Logo" mode={mode} className="brand-logo" />
        {/* <StyledSpan mode={mode} className="sidenavHoverShow">
          社交工程
        </StyledSpan> */}
      </Box>

      <Box className="sidenavHoverShow" sx={{ display: mode === "compact" ? "none" : "block" }}>
        {children || null}
      </Box>
    </BrandRoot>
  );
}
