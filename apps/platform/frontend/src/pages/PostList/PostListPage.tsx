import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { List, Card, Typography, Tag, Button, Space, Skeleton, Empty, Pagination, message } from 'antd';
import { EyeOutlined, LikeOutlined, CalendarOutlined, UserOutlined } from '@ant-design/icons';
import { listPosts } from '../../services/api';
import type { Post } from '../../types';
import dayjs from 'dayjs';

const { Title, Paragraph, Text: AntText } = Typography;

export default function PostListPage() {
  const navigate = useNavigate();
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 12;

  const fetchPosts = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await listPosts(p, pageSize);
      setPosts(res?.items || []);
      setTotal(res.total || 0);
    } catch {
      message.error('加载文章列表失败，请稍后重试');
      setPosts([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPosts(page);
  }, [fetchPosts, page]);

  const handlePageChange = (p: number) => {
    setPage(p);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          文章列表
        </Title>
        <Button type="primary" onClick={() => navigate('/posts/new')}>
          写文章
        </Button>
      </div>

      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} style={{ width: '100%' }}>
              <Skeleton active paragraph={{ rows: 3 }} />
            </Card>
          ))}
        </div>
      ) : posts.length === 0 ? (
        <Empty
          description="暂无文章"
          style={{ marginTop: 80 }}
        >
          <Button type="primary" onClick={() => navigate('/posts/new')}>
            写第一篇文章
          </Button>
        </Empty>
      ) : (
        <>
          <List
            grid={{ gutter: 16, xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 2 }}
            dataSource={posts}
            renderItem={(post: Post) => (
              <List.Item style={{ padding: 0 }}>
                <Card
                  hoverable
                  style={{ width: '100%', height: '100%' }}
                  onClick={() => navigate(`/posts/${post.id}`)}
                  bodyStyle={{ padding: 20 }}
                >
                  <Title level={5} ellipsis={{ rows: 2 }} style={{ marginBottom: 12, minHeight: 48 }}>
                    {post.title}
                  </Title>

                  <Paragraph
                    type="secondary"
                    ellipsis={{ rows: 2 }}
                    style={{ marginBottom: 16, minHeight: 44 }}
                  >
                    {post.summary || post.content?.substring(0, 200) || '暂无摘要'}
                  </Paragraph>

                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: 8,
                    }}
                  >
                    <Space size={12}>
                      <Space size={4}>
                        <UserOutlined style={{ color: '#999', fontSize: 13 }} />
                        <AntText type="secondary" style={{ fontSize: 13 }}>
                          {post.author_name || '匿名'}
                        </AntText>
                      </Space>
                      <Space size={4}>
                        <CalendarOutlined style={{ color: '#999', fontSize: 13 }} />
                        <AntText type="secondary" style={{ fontSize: 13 }}>
                          {post.created_at ? dayjs(post.created_at).format('YYYY-MM-DD') : '-'}
                        </AntText>
                      </Space>
                    </Space>
                    <Space size={12}>
                      <Space size={4}>
                        <EyeOutlined style={{ color: '#999', fontSize: 13 }} />
                        <AntText type="secondary" style={{ fontSize: 13 }}>
                          {post.view_count ?? 0}
                        </AntText>
                      </Space>
                      <Space size={4}>
                        <LikeOutlined style={{ color: '#999', fontSize: 13 }} />
                        <AntText type="secondary" style={{ fontSize: 13 }}>
                          {post.like_count ?? 0}
                        </AntText>
                      </Space>
                    </Space>
                  </div>

                  {post.tech_tags && (
                    <div style={{ marginTop: 12 }}>
                      {post.tech_tags.split(',').map((tag) => (
                        <Tag key={tag} color="blue" style={{ marginBottom: 4 }}>
                          {tag.trim()}
                        </Tag>
                      ))}
                    </div>
                  )}
                </Card>
              </List.Item>
            )}
          />

          {total > pageSize && (
            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 32 }}>
              <Pagination
                current={page}
                total={total}
                pageSize={pageSize}
                onChange={handlePageChange}
                showTotal={(t) => `共 ${t} 篇文章`}
                showSizeChanger={false}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
