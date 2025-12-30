import useAuth from 'app/hooks/useAuth';
import CreateUrl from './CreateUrl';

/**
 * Qrcode 頁面的分派器元件。
 * 根據使用者是否為 admin，渲染不同的頁面。
 */
const QrcodeDispatcher = () => {
  const { user } = useAuth();

  // 判斷使用者 email 是否為 admin
  const isAdmin = user?.name === 'admin@acercsi.com';

  return <CreateUrl isAdmin={isAdmin} />;
};

export default QrcodeDispatcher;