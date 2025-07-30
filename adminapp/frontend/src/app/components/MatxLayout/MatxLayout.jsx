import { MatxSuspense } from "app/components";
import useSettings from "app/hooks/useSettings";
import { MatxLayouts } from "./index";
import { SendtaskListProvider } from "app/contexts/SendtaskListContext";


export default function MatxLayout(props) {
  const { settings } = useSettings();
  const Layout = MatxLayouts[settings.activeLayout];

  return (
    <SendtaskListProvider>
      <MatxSuspense>
        <Layout {...props} />
      </MatxSuspense>
    </SendtaskListProvider>
  );
}
