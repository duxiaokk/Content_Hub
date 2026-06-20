import { useMemo } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Avatar, Dropdown, Layout, Menu, Space, Typography } from 'antd';
import {
  AppstoreOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  EditOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  HomeOutlined,
  LogoutOutlined,
  ProfileOutlined,
  RobotOutlined,
  UserOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { useAuthStore } from '../../stores/authStore';

const { Header, Content, Footer } = Layout;
const { Text } = Typography;

const navItems: MenuProps['items'] = [
  { key: '/', icon: <DashboardOutlined />, label: '工作台' },
  { key: '/sources', icon: <DatabaseOutlined />, label: '信源管理' },
  {
    key: 'content-hub',
    icon: <AppstoreOutlined />,
    label: '内容库',
    children: [
      { key: '/content-queue', icon: <ProfileOutlined />, label: '内容列表' },
      { key: '/posts', icon: <FileTextOutlined />, label: '文章管理' },
      { key: '/fetch-runs', icon: <FileSearchOutlined />, label: '抓取历史' },
    ],
  },
  { key: '/review-queue', icon: <EditOutlined />, label: '审核队列' },
  { key: '/digests', icon: <FileTextOutlined />, label: '日报' },
  { key: '/agent', icon: <RobotOutlined />, label: '任务调度' },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { username, role, email, logout } = useAuthStore();

  const selectedKey = useMemo(() => {
    const path = location.pathname;
    // 精确匹配
    const exactMatch = navItems?.find((item) => item && 'key' in item && item.key === path);
    if (exactMatch && typeof exactMatch.key === 'string') {
      return exactMatch.key;
    }
    // 子路由匹配
    if (path.startsWith('/posts/')) return '/posts';
    if (path.startsWith('/fetch-runs')) return '/fetch-runs';
    if (path.startsWith('/content-queue')) return '/content-queue';
    if (path.startsWith('/review-queue')) return '/review-queue';
    if (path.startsWith('/digests')) return '/digests';
    return '/';
  }, [location.pathname]);

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'info',
      disabled: true,
      label: (
        <div style={{ padding: '4px 0' }}>
          <Text strong>{username || 'Unknown User'}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {email || role || ''}
          </Text>
        </div>
      ),
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
          padding: '0 32px',
          boxShadow: '0 1px 4px rgba(0, 0, 0, 0.08)',
          position: 'sticky',
          top: 0,
          zIndex: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <Text
            strong
            style={{ fontSize: 20, color: '#1677ff', cursor: 'pointer', whiteSpace: 'nowrap' }}
            onClick={() => navigate('/')}
          >
            Content Hub
          </Text>
          <Menu
            mode="horizontal"
            selectedKeys={[selectedKey]}
            items={navItems}
            onClick={({ key }) => navigate(key)}
            style={{ borderBottom: 'none', minWidth: 600 }}
          />
        </div>

        <Dropdown menu={{ items: userMenuItems }} placement="bottomRight" arrow>
          <Space style={{ cursor: 'pointer' }}>
            <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#1677ff' }} />
            <Text>{username || '用户'}</Text>
          </Space>
        </Dropdown>
      </Header>

      <Content style={{ padding: '24px 32px', maxWidth: 1400, margin: '0 auto', width: '100%' }}>
        <Outlet />
      </Content>

      <Footer style={{ textAlign: 'center', color: '#999', background: '#fafafa' }}>
        Content Hub Console &copy; {new Date().getFullYear()}
      </Footer>
    </Layout>
  );
}
