import Box from "@mui/material/Box";
import styled from "@mui/material/styles/styled";

import { Span } from "./Typography";
// import { MatxLogo } from "app/components";
import useSettings from "app/hooks/useSettings";

// STYLED COMPONENTS
const BrandRoot = styled("div")(() => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "20px 18px 20px 29px"
}));

// const StyledSpan = styled(Span)(({ mode }) => ({
//   fontSize: 18,
//   marginLeft: ".5rem",
//   display: mode === "compact" ? "none" : "block"
// }));

//logo
const CustomLogo = styled("img")(() => ({
  width: "96px",
  height: "64px",
  objectFit: "contain"
}));

export default function Brand({ children }) {
  const { settings } = useSettings();
  const leftSidebar = settings.layout1Settings.leftSidebar;
  const { mode } = leftSidebar;

  return (
    <BrandRoot>
      <Box display="flex" alignItems="center">
        <CustomLogo src="/assets/images/logo-acsi.png" alt="Company Logo" />
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
