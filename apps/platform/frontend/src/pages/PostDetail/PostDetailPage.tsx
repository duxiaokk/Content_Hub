import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card,
  Typography,
  Tag,
  Button,
  Space,
  Spin,
  Empty,
  Descriptions,
  Divider,
  Input,
  List,
  message,
  Popconfirm,
} from 'antd';
import {
  ArrowLeftOutlined,
  LikeOutlined,
  DeleteOutlined,
  CalendarOutlined,
  UserOutlined,
  EyeOutlined,
  SendOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import {
  getPost,
  likePost,
  unlikePost,
  deletePost,
  listComments,
  createComment,
  deleteComment,
} from '../../services/api';
import type { Post, Comment } from '../../types';
import dayjs from 'dayjs';

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

export default function PostDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [post, setPost] = useState<Post | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [commentLoading, setCommentLoading] = useState(false);
  const [commentText, setCommentText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [liking, setLiking] = useState(false);

  useEffect(() => {
    if (!id) return;
    const postId = Number(id);
    if (Number.isNaN(postId)) {
      setLoading(false);
      return;
    }

    setLoading(true);
    Promise.all([getPost(postId), listComments(postId)])
      .then(([p, c]) => {
        setPost(p);
        setComments(c?.items || []);
      })
      .catch(() => {
        setPost(null);
        setComments([]);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const handleLike = async () => {
    if (!post) return;
    setLiking(true);
    try {
      await likePost(post.id);
      setPost({ ...post, like_count: post.like_count + 1, liked: true });
      message.success('点赞成功');
    } catch {
      message.error('点赞失败');
    } finally {
      setLiking(false);
    }
  };

  const handleUnlike = async () => {
    if (!post) return;
    setLiking(true);
    try {
      await unlikePost(post.id);
      setPost({ ...post, like_count: Math.max(0, post.like_count - 1), liked: false });
      message.success('取消点赞');
    } catch {
      message.error('操作失败');
    } finally {
      setLiking(false);
    }
  };

  const handleDelete = async () => {
    if (!post) return;
    try {
      await deletePost(post.id);
      message.success('文章已删除');
      navigate('/', { replace: true });
    } catch {
      message.error('删除失败');
    }
  };

  const handleCommentSubmit = async () => {
    if (!commentText.trim() || !post) return;
    setSubmitting(true);
    try {
      const newComment = await createComment(post.id, { content: commentText.trim() });
      setComments((prev) => [newComment, ...prev]);
      setCommentText('');
      message.success('评论已发布');
    } catch {
      message.error('评论发布失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteComment = async (commentId: number) => {
    if (!post) return;
    try {
      await deleteComment(post.id, commentId);
      setComments((prev) => prev.filter((c) => c.id !== commentId));
      message.success('评论已删除');
    } catch {
      message.error('删除评论失败');
    }
  };

  const refreshComments = async () => {
    if (!post) return;
    setCommentLoading(true);
    try {
      const res = await listComments(post.id);
      setComments(res?.items || []);
    } catch {
      message.error('加载评论失败');
    } finally {
      setCommentLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', marginTop: '15%' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (!post) {
    return (
      <div style={{ marginTop: 80 }}>
        <Empty description="文章不存在或已被删除">
          <Button type="primary" onClick={() => navigate('/')}>
            返回首页
          </Button>
        </Empty>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          返回首页
        </Button>
      </Space>

      <Card bodyStyle={{ padding: 32 }}>
        {/* 标题区 */}
        <Title level={2} style={{ marginBottom: 16 }}>
          {post.title}
        </Title>

        {/* 元信息 */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 24,
          }}
        >
          <Space size={16}>
            <Space size={4}>
              <UserOutlined style={{ color: '#999' }} />
              <Text type="secondary">{post.author_name || '匿名'}</Text>
            </Space>
            <Space size={4}>
              <CalendarOutlined style={{ color: '#999' }} />
              <Text type="secondary">
                {post.created_at ? dayjs(post.created_at).format('YYYY-MM-DD HH:mm') : '-'}
              </Text>
            </Space>
            {post.updated_at && post.updated_at !== post.created_at && (
              <Text type="secondary">
                (更新于 {dayjs(post.updated_at).format('YYYY-MM-DD HH:mm')})
              </Text>
            )}
          </Space>

          <Space size={16}>
            <Space size={4}>
              <EyeOutlined style={{ color: '#999' }} />
              <Text type="secondary">{post.view_count ?? 0}</Text>
            </Space>
            <Space size={4}>
              <LikeOutlined style={{ color: '#999' }} />
              <Text type="secondary">{post.like_count ?? 0}</Text>
            </Space>
          </Space>
        </div>

        {/* 标签 */}
        {post.tech_tags && (
          <div style={{ marginBottom: 24 }}>
            {post.tech_tags.split(',').map((tag) => (
              <Tag key={tag} color="blue" style={{ marginBottom: 4 }}>
                {tag.trim()}
              </Tag>
            ))}
          </div>
        )}

        <Divider style={{ margin: '16px 0 24px' }} />

        {/* 文章内容 - Markdown 渲染 */}
        <div
          style={{
            lineHeight: 1.8,
            fontSize: 16,
            color: '#333',
            wordBreak: 'break-word',
          }}
        >
          {post.content ? (
            <ReactMarkdown
              components={{
                h1: ({ children }) => <Title level={2}>{children}</Title>,
                h2: ({ children }) => <Title level={3}>{children}</Title>,
                h3: ({ children }) => <Title level={4}>{children}</Title>,
                p: ({ children }) => <Paragraph style={{ fontSize: 16, lineHeight: 1.8 }}>{children}</Paragraph>,
                code: ({ children, className }) => {
                  const inline = !className;
                  return inline ? (
                    <code style={{ background: '#f5f5f5', padding: '2px 6px', borderRadius: 4, fontSize: '0.9em' }}>
                      {children}
                    </code>
                  ) : (
                    <pre style={{ background: '#f5f5f5', padding: '16px 20px', borderRadius: 8, overflow: 'auto' }}>
                      <code>{children}</code>
                    </pre>
                  );
                },
                img: ({ src, alt }) => (
                  <img
                    src={src}
                    alt={alt}
                    style={{ maxWidth: '100%', borderRadius: 8, margin: '12px 0' }}
                  />
                ),
                blockquote: ({ children }) => (
                  <blockquote
                    style={{
                      borderLeft: '4px solid #1677ff',
                      paddingLeft: 16,
                      margin: '16px 0',
                      color: '#666',
                      background: '#f0f5ff',
                      padding: '12px 16px',
                      borderRadius: '0 8px 8px 0',
                    }}
                  >
                    {children}
                  </blockquote>
                ),
                table: ({ children }) => (
                  <table style={{ width: '100%', borderCollapse: 'collapse', margin: '16px 0' }}>
                    {children}
                  </table>
                ),
                th: ({ children }) => (
                  <th style={{ border: '1px solid #e8e8e8', padding: '8px 16px', background: '#fafafa', textAlign: 'left' }}>
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td style={{ border: '1px solid #e8e8e8', padding: '8px 16px' }}>{children}</td>
                ),
              }}
            >
              {post.content}
            </ReactMarkdown>
          ) : (
            <Empty description="暂无内容" />
          )}
        </div>

        <Divider />

        {/* 操作按钮 */}
        <Space size={16}>
          <Button
            icon={<LikeOutlined />}
            onClick={handleLike}
            loading={liking}
          >
            点赞 ({post.like_count})
          </Button>
          <Popconfirm title="确定删除这篇文章吗？" onConfirm={handleDelete} okText="确定" cancelText="取消">
            <Button danger icon={<DeleteOutlined />}>
              删除文章
            </Button>
          </Popconfirm>
        </Space>
      </Card>

      {/* 评论区 */}
      <Card title={`评论 (${comments.length})`} style={{ marginTop: 24 }} bodyStyle={{ padding: 24 }}>
        {/* 发表评论 */}
        <div style={{ marginBottom: 24 }}>
          <TextArea
            rows={3}
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            placeholder="写下你的评论..."
            maxLength={500}
            showCount
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleCommentSubmit}
            loading={submitting}
            disabled={!commentText.trim()}
            style={{ marginTop: 12 }}
          >
            发表评论
          </Button>
        </div>

        <Divider style={{ margin: '12px 0 16px' }} />

        {/* 评论列表 */}
        {commentLoading ? (
          <Spin />
        ) : comments.length === 0 ? (
          <Empty description="暂无评论，来发表第一条评论吧" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            dataSource={comments}
            renderItem={(comment: Comment) => (
              <List.Item
                actions={[
                  <Popconfirm
                    key="delete"
                    title="确定删除此评论？"
                    onConfirm={() => handleDeleteComment(comment.id)}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button type="link" size="small" danger>
                      删除
                    </Button>
                  </Popconfirm>,
                ]}
              >
                <List.Item.Meta
                  avatar={
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: '50%',
                        background: '#1677ff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#fff',
                        fontSize: 14,
                        fontWeight: 600,
                      }}
                    >
                      {(comment.username || '?')[0].toUpperCase()}
                    </div>
                  }
                  title={
                    <Space>
                      <Text strong>{comment.username || '匿名用户'}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {comment.created_at ? dayjs(comment.created_at).format('YYYY-MM-DD HH:mm') : '-'}
                      </Text>
                    </Space>
                  }
                  description={
                    <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                      {comment.content}
                    </Paragraph>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>
    </div>
  );
}
