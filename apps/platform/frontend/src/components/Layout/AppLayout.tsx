import { useMemo } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Avatar, Dropdown, Typography, Space } from 'antd';
import {
  HomeOutlined,
  EditOutlined,
  RobotOutlined,
  LogoutOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useAuthStore } from '../../stores/authStore';
import type { MenuProps } from 'antd';

const { Header, Content, Footer } = Layout;
const { Text } = Typography;

const navItems: MenuProps['items'] = [
  { key: '/', icon: <HomeOutlined />, label: '首页' },
  { key: '/create', icon: <EditOutlined />, label: '写文章' },
  { key: '/agent', icon: <RobotOutlined />, label: 'Agent 控制台' },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { username, role, email, logout } = useAuthStore();

  const selectedKey = useMemo(() => {
    const path = location.pathname;
    if (path === '/') return '/';
    if (path.startsWith('/create')) return '/create';
    if (path.startsWith('/agent')) return '/agent';
    if (path.startsWith('/post/')) return '/';
    return '/';
  }, [location.pathname]);

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'info',
      label: (
        <div style={{ padding: '4px 0' }}>
          <Text strong>{username || '未知用户'}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {email || role || ''}
          </Text>
        </div>
      ),
      disabled: true,
    },
    { type: 'divider' },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: () => {
        logout();
        navigate('/login', { replace: true });
      },
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: '#fff',
          padding: '0 40px',
          boxShadow: '0 1px 4px rgba(0, 0, 0, 0.08)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        {/* Logo + 导航 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
          <Text
            strong
            style={{
              fontSize: 20,
              color: '#1677ff',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
            onClick={() => navigate('/')}
          >
            Ado_Jk
          </Text>
          <Menu
            mode="horizontal"
            selectedKeys={[selectedKey]}
            items={navItems}
            onClick={({ key }) => navigate(key)}
            style={{ borderBottom: 'none', minWidth: 320 }}
          />
        </div>

        {/* 用户菜单 */}
        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight" arrow>
          <Space style={{ cursor: 'pointer' }}>
            <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#1677ff' }} />
            <Text>{username || '用户'}</Text>
          </Space>
        </Dropdown>
      </Header>

      <Content style={{ padding: '24px 40px', maxWidth: 1200, margin: '0 auto', width: '100%' }}>
        <Outlet />
      </Content>

      <Footer style={{ textAlign: 'center', color: '#999', background: '#fafafa' }}>
        Ado_Jk Platform &copy; {new Date().getFullYear()} &mdash; Multi-Agent Content Orchestration
      </Footer>
    </Layout>
  );
}
